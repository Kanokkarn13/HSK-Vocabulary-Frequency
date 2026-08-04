"""Production Transform step shared by Notebook and Airflow.

The rules mirror the reviewed Notebook 02 pipeline: deduplicate repeated
listening clauses, convert traditional to simplified Chinese, use Jieba with
the project HSK boundary strategy, then attribute safe components.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

from etl.hsk_components import component_levels
from etl.logging_config import get_logger
from etl.tokenizer import DEFAULT_HMM, DEFAULT_MAX_HSK_CHARS, DEFAULT_STRATEGY, load_hsk_words, segment


LOGGER = get_logger(__name__)
CLAUSE_SPLIT_RE = re.compile(r"(?<=[,。!?、;])")
EXACT_MIN_LEN = 4
MAX_BLOCK = 8
MIN_SINGLE_LEN = 4
SIM_THRESHOLD = 0.82
_OPENCC = None
_OPENCC_INITIALIZED = False


def collapse_exact_repeats(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        best_length = 0
        max_length = (len(text) - index) // 2
        for length in range(max_length, EXACT_MIN_LEN - 1, -1):
            if text[index : index + length] == text[index + length : index + 2 * length]:
                best_length = length
                break
        if best_length:
            repeated = text[index : index + best_length]
            result.append(repeated)
            index += best_length * 2
            while text[index : index + best_length] == repeated:
                index += best_length
        else:
            result.append(text[index])
            index += 1
    return "".join(result)


def _split_clauses(text: str) -> list[str]:
    return [clause for clause in CLAUSE_SPLIT_RE.split(text) if clause.strip()]


def _block_matches(clauses: list[str], first: int, second: int, block_len: int) -> bool:
    return all(
        SequenceMatcher(None, clauses[first + offset], clauses[second + offset]).ratio() >= SIM_THRESHOLD
        for offset in range(block_len)
    )


def dedupe_repeated_clauses(clauses: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(clauses):
        matched = False
        upper = min(MAX_BLOCK, (len(clauses) - index) // 2)
        for block_len in range(upper, 0, -1):
            if block_len == 1 and len(clauses[index]) < MIN_SINGLE_LEN:
                continue
            if index + 2 * block_len <= len(clauses) and _block_matches(clauses, index, index + block_len, block_len):
                result.extend(clauses[index : index + block_len])
                index += block_len
                while index + block_len <= len(clauses) and _block_matches(clauses, index - block_len, index, block_len):
                    index += block_len
                matched = True
                break
        if not matched:
            result.append(clauses[index])
            index += 1
    return result


def clean_text(text: str, source_type: str) -> str:
    value = "" if text is None or pd.isna(text) else str(text)
    if source_type == "listening":
        value = "".join(dedupe_repeated_clauses(_split_clauses(collapse_exact_repeats(value))))
    try:
        global _OPENCC, _OPENCC_INITIALIZED
        if not _OPENCC_INITIALIZED:
            from opencc import OpenCC

            _OPENCC = OpenCC("t2s")
            _OPENCC_INITIALIZED = True
        value = _OPENCC.convert(value)
    except ImportError:
        # The lightweight Load image can still run tests; the full ETL image
        # installs opencc and uses the production conversion path.
        LOGGER.warning("opencc is not installed; leaving text unchanged")
    return value


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _quality_report(frame: pd.DataFrame, hsk_words: dict[str, int]) -> dict[str, Any]:
    total = int(frame["count"].sum()) if not frame.empty else 0
    matched = int(frame.loc[frame["match_type"].isin(["direct", "decomposed"]), "count"].sum()) if total else 0
    level_one = int(frame.loc[frame["level"] == 1, "count"].sum()) if total else 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": int(len(frame)),
        "token_occurrences": total,
        "matched_occurrences": matched,
        "match_rate": round(matched / total, 6) if total else 0.0,
        "hsk1_occurrence_share": round(level_one / total, 6) if total else 0.0,
        "unmatched_occurrences": total - matched,
        "wordlist_size": len(hsk_words),
        "level_counts": {
            str(int(level)): int(count)
            for level, count in frame.loc[frame["level"].notna()].groupby("level")["count"].sum().items()
        },
        "config": {
            "hmm": DEFAULT_HMM,
            "strategy": DEFAULT_STRATEGY,
            "max_hsk_chars": DEFAULT_MAX_HSK_CHARS,
        },
    }


def _checksum(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values(["exam_id", "source_type", "word", "match_type"], kind="stable")
    return hashlib.sha256(ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def transform_raw(
    raw_path: str | Path,
    wordlist_path: str | Path,
    output_dir: str | Path,
    *,
    quality_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Transform a staged raw snapshot into HSK component counts."""

    raw = pd.read_parquet(raw_path).drop_duplicates(["exam_id", "source_type"])
    required = {"exam_id", "hsk_level", "source_type", "text"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Raw snapshot is missing columns: {sorted(missing)}")
    hsk_words = load_hsk_words(wordlist_path)
    if not hsk_words:
        raise ValueError("Wordlist contains no valid HSK words")

    rows: list[dict[str, Any]] = []
    for source in raw.itertuples(index=False):
        text = clean_text(source.text, str(source.source_type))
        tokens = segment(text, hmm=DEFAULT_HMM, hsk_words=set(hsk_words), strategy=DEFAULT_STRATEGY)
        for token, count in Counter(tokens).items():
            components, levels, match_type = component_levels(
                token,
                hsk_words,
                max_word_chars=DEFAULT_MAX_HSK_CHARS,
            )
            if components is None:
                components, levels, match_type = [token], [None], "unmatched"
            for component, level in zip(components, levels):
                rows.append(
                    {
                        "exam_id": source.exam_id,
                        "hsk_level": source.hsk_level,
                        "source_type": source.source_type,
                        "word": component,
                        "level": level,
                        "match_type": match_type,
                        "count": int(count),
                        "raw_token": token,
                    }
                )

    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("Transform produced no token rows")
    result = (
        result.groupby(
            ["exam_id", "hsk_level", "source_type", "word", "level", "match_type", "raw_token"],
            dropna=False,
            as_index=False,
        )["count"].sum()
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    counts_path = output / "hsk_component_counts.parquet"
    _atomic_parquet(result, counts_path)
    csv_path = output / "hsk_component_counts.csv"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    quality = _quality_report(result, hsk_words)
    quality["checksum"] = _checksum(result)
    report_path = Path(quality_report_path) if quality_report_path else output / "transform_quality_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=report_path.parent, suffix=".json", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(quality, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        temporary.replace(report_path)
    finally:
        temporary.unlink(missing_ok=True)
    LOGGER.info("Transform produced %d rows at match_rate=%s", len(result), quality["match_rate"])
    return {
        "status": "updated",
        "counts_path": str(counts_path),
        "quality_report_path": str(report_path),
        **quality,
    }


__all__ = [
    "clean_text",
    "collapse_exact_repeats",
    "dedupe_repeated_clauses",
    "transform_raw",
]
