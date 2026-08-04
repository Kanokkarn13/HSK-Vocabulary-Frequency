from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import requests

from etl.extract_wordlist import (
    dataframe_checksum,
    fetch_records,
    normalize_records,
    run,
    validate_wordlist,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class ErrorResponse:
    def __init__(self, error):
        self.error = error

    def raise_for_status(self):
        raise self.error

    def json(self):
        return {}


def test_fetch_records_paginates_and_deduplicates_ids():
    session = FakeSession(
        [
            FakeResponse(
                {
                    "data": [{"id": 1, "word": "你", "level": 1}, {"id": 2, "word": "好", "level": 1}],
                    "metadata": {"has_next": True, "total_records": 3},
                }
            ),
            FakeResponse(
                {
                    "data": [{"id": 2, "word": "好", "level": 1}, {"id": 3, "word": "你好", "level": 1}],
                    "metadata": {"has_next": False, "total_records": 3},
                }
            ),
        ]
    )

    records = fetch_records("https://example.test/words", "secret", session=session)

    assert [row["id"] for row in records] == [1, 2, 3]
    assert [call[1]["params"]["page"] for call in session.calls] == [1, 2]
    assert session.calls[0][1]["headers"] == {"X-API-KEY": "secret"}


def test_fetch_records_propagates_unauthorized_without_retrying():
    session = FakeSession([ErrorResponse(requests.HTTPError("401 Client Error"))])
    with pytest.raises(requests.HTTPError, match="401"):
        fetch_records("https://example.test/words", session=session)
    assert len(session.calls) == 1


def test_fetch_records_rejects_wrong_schema():
    session = FakeSession([FakeResponse({"data": {"word": "bad"}})])
    with pytest.raises(ValueError, match="data must be a list"):
        fetch_records("https://example.test/words", session=session)


def test_fetch_records_propagates_timeout_for_caller_retry_policy():
    class TimeoutSession:
        def get(self, *args, **kwargs):
            raise requests.Timeout("upstream timeout")

    with pytest.raises(requests.Timeout, match="timeout"):
        fetch_records("https://example.test/words", session=TimeoutSession())


def test_normalize_and_validate_wordlist():
    frame = normalize_records(
        [
            {"id": 1, "word": "  你 ", "level": "1", "definition": "you"},
            {"id": 2, "word": "你好", "level": 2, "definition": "hello"},
        ]
    )

    metrics = validate_wordlist(frame)

    assert frame["word"].tolist() == ["你", "你好"]
    assert str(frame["level"].dtype) == "Int64"
    assert metrics["row_count"] == 2
    assert metrics["level_counts"] == {"1": 1, "2": 1}


def test_validate_rejects_duplicate_words():
    frame = normalize_records(
        [{"id": 1, "word": "行", "level": 1}, {"id": 2, "word": "行", "level": 2}]
    )

    with pytest.raises(ValueError, match="duplicate words"):
        validate_wordlist(frame)


def test_checksum_is_independent_of_api_order():
    first = normalize_records(
        [{"id": 1, "word": "你", "level": 1}, {"id": 2, "word": "你好", "level": 1}]
    )
    second = normalize_records(
        [{"id": 2, "word": "你好", "level": 1}, {"id": 1, "word": "你", "level": 1}]
    )

    assert dataframe_checksum(first) == dataframe_checksum(second)


def test_run_uses_existing_snapshot_when_api_is_not_configured(tmp_path):
    snapshot = normalize_records([{"id": 1, "word": "你", "level": 1}])
    snapshot.to_parquet(tmp_path / "hsk_wordlist.parquet", index=False)

    result = run(
        output_dir=tmp_path,
        api_url="",
        require_api=False,
        now=datetime.now(timezone.utc) + timedelta(days=8),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "api_not_configured"
    assert result["row_count"] == 1


def test_run_reports_no_change_when_api_content_matches(monkeypatch, tmp_path):
    snapshot = normalize_records([{"id": 1, "word": "你", "level": 1}])
    snapshot.to_parquet(tmp_path / "hsk_wordlist.parquet", index=False)
    monkeypatch.setattr(
        "etl.extract_wordlist.fetch_records",
        lambda *args, **kwargs: [{"id": 1, "word": "你", "level": 1}],
    )

    result = run(
        output_dir=tmp_path,
        api_url="https://example.test/words",
        force=True,
    )

    assert result["status"] == "unchanged"
    assert result["changed"] is False
    assert result["reason"] == "no_change"


def test_run_quarantines_small_number_of_invalid_api_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("HSK_WORDLIST_MAX_INVALID_RATE", "0.50")
    monkeypatch.setattr(
        "etl.extract_wordlist.fetch_records",
        lambda *args, **kwargs: [
            {"id": 1, "word": "你", "level": 1},
            {"id": 2, "word": "bad", "level": None},
        ],
    )

    result = run(output_dir=tmp_path, api_url="https://example.test/words", force=True)

    assert result["status"] == "updated"
    assert result["quarantined_rows"] == 1
    assert (tmp_path / "hsk_wordlist_quarantine.csv").exists()
    assert result["row_count"] == 1


def test_run_rejects_too_many_invalid_api_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "etl.extract_wordlist.fetch_records",
        lambda *args, **kwargs: [{"id": i, "word": f"bad-{i}", "level": None} for i in range(3)],
    )

    with pytest.raises(ValueError, match="exceeds quarantine limits"):
        run(
            output_dir=tmp_path,
            api_url="https://example.test/words",
            force=True,
            now=datetime.now(timezone.utc) + timedelta(days=8),
        )


def test_run_rejects_invalid_existing_snapshot_without_api(tmp_path):
    snapshot = pd.DataFrame([{"id": 1, "word": "坏", "level": None}])
    snapshot.to_parquet(tmp_path / "hsk_wordlist.parquet", index=False)

    with pytest.raises(ValueError, match="snapshot is invalid"):
        run(output_dir=tmp_path, api_url="", require_api=False)
