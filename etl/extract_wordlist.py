"""Fetch, validate, and snapshot the HSK wordlist.

The source API is treated as an external input.  A successful fetch is written
to temporary files first and then promoted with atomic renames, so a failed or
partial request never replaces the last usable snapshot.

The function returns only small metadata suitable for an Airflow XCom.  The
wordlist itself stays on disk as Parquet/CSV and is never passed through XCom.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOGGER = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DEFAULT_PER_PAGE = 1000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_AGE = timedelta(days=7)
OUTPUT_COLUMNS = [
    "id",
    "word",
    "pinyin",
    "definition",
    "definition_th",
    "level",
    "example_sentence",
    "example_pinyin",
]
REQUIRED_COLUMNS = {"word", "level"}


def build_http_session() -> requests.Session:
    """Create a session that retries transient API responses only."""

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _records_from_response(raw: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract records and pagination metadata from supported API responses."""

    if isinstance(raw, list):
        records, metadata = raw, {}
    elif isinstance(raw, dict):
        records = raw.get("data", raw.get("results"))
        metadata = raw.get("metadata", {})
    else:
        raise ValueError("Wordlist API response must be a JSON list or object")

    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("Wordlist API response data must be a list of objects")
    if not isinstance(metadata, dict):
        raise ValueError("Wordlist API metadata must be an object")
    return records, metadata


def fetch_records(
    api_url: str,
    api_key: str = "",
    *,
    per_page: int = DEFAULT_PER_PAGE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch every page from the HSK wordlist API.

    401/403 and schema errors fail immediately.  Connection errors and the
    transient statuses configured in :func:`build_http_session` are retried by
    requests/urllib3.
    """

    if not api_url.strip():
        raise ValueError("HSK_WORDLIST_API_URL is empty")
    if not api_url.lower().startswith("https://"):
        raise ValueError("Wordlist API URL must use HTTPS")
    if per_page <= 0:
        raise ValueError("per_page must be positive")

    client = session or build_http_session()
    headers = {"X-API-KEY": api_key} if api_key else {}
    all_records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    page = 1

    try:
        while True:
            response = client.get(
                api_url,
                headers=headers,
                params={"page": page, "per_page": per_page},
                timeout=timeout,
            )
            response.raise_for_status()
            records, metadata = _records_from_response(response.json())

            new_records = []
            for record in records:
                record_key = record.get("id", record.get("word"))
                if record_key is None:
                    raise ValueError(f"Wordlist record on page {page} has no id or word")
                record_key = str(record_key)
                if record_key not in seen_keys:
                    seen_keys.add(record_key)
                    new_records.append(record)

            all_records.extend(new_records)
            LOGGER.info(
                "Fetched wordlist page=%s new=%s total=%s expected=%s",
                page,
                len(new_records),
                len(all_records),
                metadata.get("total_records", "unknown"),
            )

            has_next = metadata.get("has_next")
            if has_next is False or (has_next is None and len(records) < per_page):
                break
            page += 1
    finally:
        if session is None:
            client.close()

    if not all_records:
        raise ValueError("Wordlist API returned zero records")
    return all_records


def normalize_records(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Normalize API records into the stable project snapshot schema."""

    frame = pd.DataFrame(list(records))
    if frame.empty:
        raise ValueError("Cannot normalize an empty wordlist")

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Wordlist response is missing required columns: {sorted(missing)}")

    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[OUTPUT_COLUMNS].copy()
    frame["word"] = frame["word"].astype("string").str.strip()
    frame["level"] = pd.to_numeric(frame["level"], errors="coerce")

    # Keep integer-looking levels as nullable integers in both Parquet and CSV.
    frame["level"] = frame["level"].astype("Int64")
    return frame


def validate_wordlist(frame: pd.DataFrame, *, min_rows: int = 1) -> dict[str, Any]:
    """Validate the snapshot and return small quality metrics."""

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Wordlist snapshot is missing columns: {sorted(missing)}")
    if len(frame) < min_rows:
        raise ValueError(f"Wordlist has {len(frame)} rows; expected at least {min_rows}")

    blank_words = frame["word"].isna() | frame["word"].astype("string").str.strip().eq("")
    if blank_words.any():
        raise ValueError(f"Wordlist contains {int(blank_words.sum())} blank words")

    levels = pd.to_numeric(frame["level"], errors="coerce")
    invalid_levels = levels.isna() | (levels % 1 != 0) | (levels < 1) | (levels > 9)
    if invalid_levels.any():
        raise ValueError(f"Wordlist contains {int(invalid_levels.sum())} invalid HSK levels")

    duplicate_words = frame["word"].astype("string").duplicated(keep=False)
    if duplicate_words.any():
        examples = frame.loc[duplicate_words, "word"].astype(str).unique()[:5].tolist()
        raise ValueError(f"Wordlist contains duplicate words, examples: {examples}")

    return {
        "row_count": int(len(frame)),
        "level_counts": {
            str(int(level)): int(count)
            for level, count in frame.groupby("level", dropna=False).size().items()
        },
    }


def _invalid_record_mask(frame: pd.DataFrame) -> pd.Series:
    """Rows that are safe to quarantine before validating the full snapshot."""

    blank_words = frame["word"].isna() | frame["word"].astype("string").str.strip().eq("")
    levels = pd.to_numeric(frame["level"], errors="coerce")
    invalid_levels = levels.isna() | (levels % 1 != 0) | (levels < 1) | (levels > 9)
    return blank_words | invalid_levels


def dataframe_checksum(frame: pd.DataFrame) -> str:
    """Return an order-independent checksum for normalized wordlist content."""

    normalized = frame[OUTPUT_COLUMNS].copy()
    normalized = normalized.sort_values(["word", "level"], kind="stable", na_position="last")
    payload = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_write(frame: pd.DataFrame, output_dir: Path, filename: str, writer: Any) -> None:
    """Write one artifact beside the destination, then atomically promote it."""

    destination = output_dir / filename
    suffix = destination.suffix or ".tmp"
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=suffix, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        writer(frame, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_snapshot(frame: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(frame, output_dir, "hsk_wordlist.parquet", lambda data, path: data.to_parquet(path, index=False))
    _atomic_write(
        frame,
        output_dir,
        "hsk_wordlist.csv",
        lambda data, path: data.to_csv(path, index=False, encoding="utf-8-sig"),
    )
    _atomic_write(
        frame[["word", "level"]],
        output_dir,
        "hsk_word_level_lookup.csv",
        lambda data, path: data.to_csv(path, index=False, encoding="utf-8-sig"),
    )


def _write_metadata(output_dir: Path, metadata: dict[str, Any]) -> None:
    destination = output_dir / "hsk_wordlist_metadata.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output_dir, suffix=".json", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _existing_snapshot(output_dir: Path) -> tuple[pd.DataFrame | None, str | None]:
    path = output_dir / "hsk_wordlist.parquet"
    if not path.exists():
        return None, None
    frame = normalize_records(pd.read_parquet(path).to_dict(orient="records"))
    try:
        validate_wordlist(frame)
    except ValueError as exc:
        # Keep the frame available so a configured API can repair a bad old
        # snapshot.  The caller will refuse to use it when no API is available.
        LOGGER.warning("Existing wordlist snapshot failed validation: %s", exc)
        return frame, None
    return frame, dataframe_checksum(frame)


def run(
    *,
    output_dir: str | Path = DEFAULT_DATA_DIR,
    api_url: str | None = None,
    api_key: str | None = None,
    force: bool = False,
    max_age: timedelta = DEFAULT_MAX_AGE,
    require_api: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh the snapshot when needed and return run metadata.

    If the API is not configured but a valid snapshot exists, the default
    development behavior is to keep using that snapshot and return ``skipped``.
    Set ``require_api=True`` for scheduled/production runs that must verify the
    upstream source instead of accepting a stale local snapshot.
    """

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    current_time = now or datetime.now(timezone.utc)
    existing, existing_checksum = _existing_snapshot(destination)
    snapshot_path = destination / "hsk_wordlist.parquet"

    configured_url = (api_url if api_url is not None else os.getenv("HSK_WORDLIST_API_URL", "")).strip()
    configured_key = api_key if api_key is not None else os.getenv("HSK_WORDLIST_API_KEY", "")

    age = None
    if snapshot_path.exists():
        modified = datetime.fromtimestamp(snapshot_path.stat().st_mtime, tz=timezone.utc)
        age = current_time - modified

    if (
        existing is not None
        and existing_checksum is not None
        and not force
        and age is not None
        and age <= max_age
    ):
        return {
            "status": "skipped",
            "changed": False,
            "reason": "snapshot_fresh",
            "checksum": existing_checksum,
            "row_count": int(len(existing)),
            "snapshot_path": str(snapshot_path),
        }

    if not configured_url:
        if existing is not None and existing_checksum is not None and not require_api:
            LOGGER.warning("HSK_WORDLIST_API_URL is not configured; using existing snapshot")
            return {
                "status": "skipped",
                "changed": False,
                "reason": "api_not_configured",
                "checksum": existing_checksum,
                "row_count": int(len(existing)),
                "snapshot_path": str(snapshot_path),
            }
        if existing is not None and existing_checksum is None:
            raise ValueError(
                "Existing HSK wordlist snapshot is invalid; configure HSK_WORDLIST_API_URL "
                "to refresh it before continuing"
            )
        raise ValueError("HSK_WORDLIST_API_URL is required to create or refresh the snapshot")

    fetched_at = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    fetched = normalize_records(fetch_records(configured_url, configured_key))
    invalid_mask = _invalid_record_mask(fetched)
    quarantined_rows = int(invalid_mask.sum())
    max_invalid = int(os.getenv("HSK_WORDLIST_MAX_INVALID_ROWS", "10"))
    max_invalid_rate = float(os.getenv("HSK_WORDLIST_MAX_INVALID_RATE", "0.01"))
    if quarantined_rows:
        invalid_rate = quarantined_rows / max(len(fetched), 1)
        if quarantined_rows > max_invalid or invalid_rate > max_invalid_rate:
            raise ValueError(
                f"Wordlist contains {quarantined_rows} invalid rows; exceeds quarantine limits "
                f"({max_invalid} rows/{max_invalid_rate:.2%})"
            )
        quarantine_path = destination / "hsk_wordlist_quarantine.csv"
        _atomic_write(
            fetched.loc[invalid_mask],
            destination,
            quarantine_path.name,
            lambda data, path: data.to_csv(path, index=False, encoding="utf-8-sig"),
        )
        fetched = fetched.loc[~invalid_mask].reset_index(drop=True)
    quality = validate_wordlist(fetched)
    checksum = dataframe_checksum(fetched)

    if existing_checksum == checksum and existing is not None:
        status = "unchanged"
        changed = False
    else:
        _write_snapshot(fetched, destination)
        status = "updated"
        changed = True

    metadata = {
        "schema_version": 1,
        "status": status,
        "reason": "no_change" if not changed else "snapshot_refreshed",
        "changed": changed,
        "snapshot_at": fetched_at,
        "checksum": checksum,
        "row_count": quality["row_count"],
        "quarantined_rows": quarantined_rows,
        "level_counts": quality["level_counts"],
        "source": "hsk_wordlist_api",
        "api_url": configured_url,
    }
    _write_metadata(destination, metadata)
    LOGGER.info("Wordlist snapshot %s: rows=%s checksum=%s", status, quality["row_count"], checksum)
    return {**metadata, "snapshot_path": str(snapshot_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="fetch even when the snapshot is fresh")
    parser.add_argument("--require-api", action="store_true", help="fail if the API is not configured")
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE.total_seconds() / 3600)
    args = parser.parse_args()
    result = run(
        force=args.force,
        require_api=args.require_api,
        max_age=timedelta(hours=args.max_age_hours),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
