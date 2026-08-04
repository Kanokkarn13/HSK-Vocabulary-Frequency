"""Tests for the Jieba evaluation harness (no DB, no full corpus)."""
import csv
from pathlib import Path

import pytest

from etl.tokenizer import build_tokenizer
from scripts.evaluate_jieba import (
    HSK_LEVELS,
    MODES,
    Mode,
    _boundaries,
    _case_metrics,
    _cjk_only,
    _require,
    _write_csv,
)

CASES_PATH = Path(__file__).resolve().parent.parent / "data/validation/segmentation_cases.csv"


def _read_cases_fixture() -> list[dict[str, str]]:
    with open(CASES_PATH, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_segmentation_cases_fixture_is_tracked():
    # The case_* metrics silently disappear if this file isn't in the repo.
    assert CASES_PATH.exists()
    assert len(_read_cases_fixture()) >= 20


def test_write_csv_uses_union_of_keys_across_rows(tmp_path):
    # Modes emit different optional columns; fieldnames from rows[0] alone
    # would raise "dict contains fields not in fieldnames".
    rows: list[dict[str, object]] = [
        {"mode": "a", "level_1_occurrences": 1},
        {"mode": "b", "level_1_occurrences": 2, "level_7_occurrences": 3},
    ]
    path = tmp_path / "summary.csv"

    _write_csv(path, rows)

    with open(path, encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert list(written[0]) == ["mode", "level_1_occurrences", "level_7_occurrences"]
    assert written[0]["level_7_occurrences"] == ""
    assert written[1]["level_7_occurrences"] == "3"


def test_write_csv_skips_empty_rows(tmp_path):
    path = tmp_path / "nested" / "empty.csv"

    _write_csv(path, [])

    assert not path.exists()


def test_cjk_only_drops_punctuation_and_empty_tokens():
    assert _cjk_only(["我", "很好", ",", "你呢", "?"]) == ["我", "很好", "你呢"]
    assert _cjk_only(["HSK三级", "考试"]) == ["三级", "考试"]


def test_boundaries_are_cumulative_internal_offsets():
    assert _boundaries(["我", "很好", "吗"]) == {1, 3}
    assert _boundaries(["单"]) == set()
    assert _boundaries([]) == set()


def test_case_metrics_ignore_punctuation_instead_of_misaligning():
    # segment() drops the comma, so an expected list containing it must be
    # normalised -- otherwise offsets on the two sides describe different
    # strings and precision is reported against accidental overlaps.
    cases = [{"text": "我很好,你呢", "expected_tokens": "我|很|好|,|你|呢"}]
    mode = Mode("baseline_hmm_true", hmm=True, use_hsk=False)

    metrics = _case_metrics(cases, {}, mode, build_tokenizer())

    assert metrics["case_count"] == 1
    assert metrics["case_non_cjk_stripped"] == 1
    assert metrics["case_exact_accuracy"] == 1.0
    assert metrics["case_boundary_precision"] == 1.0
    assert metrics["case_boundary_recall"] == 1.0


def test_case_metrics_returns_empty_without_cases():
    mode = Mode("baseline_hmm_true", hmm=True, use_hsk=False)

    assert _case_metrics([], {}, mode, build_tokenizer()) == {}


def test_case_metrics_cover_every_mode_on_the_tracked_fixture():
    cases = _read_cases_fixture()
    hsk_words = {"图书馆": 3, "答题卡": 4, "多长时间": 2}
    tokenizer = build_tokenizer()

    for mode in MODES:
        metrics = _case_metrics(cases, hsk_words, mode, tokenizer)

        assert metrics["case_count"] == len(cases)
        assert 0.0 <= metrics["case_boundary_f1"] <= 1.0


def test_modes_have_unique_names_and_valid_strategies():
    names = [mode.name for mode in MODES]

    assert len(names) == len(set(names))
    assert all(mode.strategy in {"merge", "dp"} for mode in MODES)


def test_hsk_levels_cover_the_range_load_hsk_words_accepts():
    assert list(HSK_LEVELS) == list(range(1, 10))


def test_require_reports_the_missing_path_and_a_hint(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        _require(tmp_path / "absent.csv", "run the pipeline first")

    message = str(excinfo.value)
    assert "absent.csv" in message
    assert "run the pipeline first" in message


def test_require_returns_existing_path(tmp_path):
    path = tmp_path / "present.csv"
    path.write_text("word\n", encoding="utf-8")

    assert _require(path, "unused") == path
