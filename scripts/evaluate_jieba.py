"""Compare Jieba configurations on the project's raw extraction snapshot.

This is a diagnostic experiment. It does not overwrite word_counts.parquet.
Run from the repository root:

    python -m scripts.evaluate_jieba

Required inputs (both are gitignored, so a fresh clone must produce them first
by running the extraction pipeline -- see README):

    data/raw/raw_extractions.csv        `python -m etl.extract_pdf` et al.
    data/processed/hsk_wordlist.csv     `python -m etl.extract_wordlist`

The segmentation cases (data/validation/segmentation_cases.csv) are tracked, so
the case_* metrics are reproducible from a clean checkout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import jieba

from etl.tokenizer import build_tokenizer, load_hsk_words, segment


ROOT = Path(__file__).resolve().parents[1]

# Boundary-change dumps are diagnostic samples, not a complete audit log; the
# cap keeps a pathological run from writing a multi-gigabyte CSV. Truncation is
# reported in the summary so a capped sample is never mistaken for the total.
MAX_BOUNDARY_CHANGES = 5000

# `segment()` discards every non-CJK token, so metrics that align predicted and
# expected tokens by character offset must compare CJK-only text on both sides.
_NON_CJK_RE = re.compile(r"[^一-鿿]")

# HSK 3.0 levels; `load_hsk_words` accepts 1-9, so every column is emitted
# unconditionally to keep the CSV schema identical across modes.
HSK_LEVELS = range(1, 10)


@dataclass(frozen=True)
class Mode:
    """One tokenizer configuration under test.

    Configuration is explicit rather than parsed back out of the mode name, so
    adding a mode cannot silently disagree with itself between the corpus
    metrics and the segmentation-case metrics.
    """

    name: str
    hmm: bool
    use_hsk: bool
    strategy: str = "merge"


MODES = (
    Mode("baseline_hmm_true", hmm=True, use_hsk=False),
    Mode("baseline_hmm_false", hmm=False, use_hsk=False),
    Mode("hsk_merge_hmm_true", hmm=True, use_hsk=True, strategy="merge"),
    Mode("hsk_merge_hmm_false", hmm=False, use_hsk=True, strategy="merge"),
    Mode("hsk_dp_hmm_true", hmm=True, use_hsk=True, strategy="dp"),
)


def _require(path: Path, hint: str) -> Path:
    """Fail with an actionable message instead of a bare FileNotFoundError."""

    if not path.exists():
        raise SystemExit(f"missing required input: {path}\n  {hint}")
    return path


def _read_raw(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write ``rows`` using the union of their keys, in first-seen order.

    Taking fieldnames from ``rows[0]`` alone raises ValueError as soon as one
    row carries a key the first row lacks.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


def _read_cases(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _cjk_only(tokens: list[str]) -> list[str]:
    """Drop non-CJK characters so expected tokens align with `segment()` output.

    A case written as ``我很好,你呢?`` expects a ``,`` token that `segment()`
    never emits. Without this the cumulative character offsets on the two sides
    describe different strings and the boundary scores are silently wrong.
    """

    stripped = (_NON_CJK_RE.sub("", token) for token in tokens)
    return [token for token in stripped if token]


def _boundaries(tokens: list[str]) -> set[int]:
    """Cumulative character offsets of the internal token boundaries."""

    offsets: set[int] = set()
    cursor = 0
    for token in tokens[:-1]:
        cursor += len(token)
        offsets.add(cursor)
    return offsets


def _case_metrics(
    cases: list[dict[str, str]],
    hsk_words: dict[str, int],
    mode: Mode,
    tokenizer: jieba.Tokenizer,
) -> dict[str, object]:
    if not cases:
        return {}
    vocabulary = set(hsk_words) if mode.use_hsk else None
    exact = 0
    non_cjk_cases = 0
    true_positive = predicted_total = expected_total = 0
    for case in cases:
        raw_expected = case["expected_tokens"].split("|")
        expected = _cjk_only(raw_expected)
        if expected != raw_expected:
            non_cjk_cases += 1
        predicted = segment(
            case["text"],
            tokenizer=tokenizer,
            hmm=mode.hmm,
            hsk_words=vocabulary,
            strategy=mode.strategy,
        )
        exact += predicted == expected
        expected_boundaries = _boundaries(expected)
        predicted_boundaries = _boundaries(predicted)
        true_positive += len(expected_boundaries & predicted_boundaries)
        expected_total += len(expected_boundaries)
        predicted_total += len(predicted_boundaries)
    precision = true_positive / predicted_total if predicted_total else 0
    recall = true_positive / expected_total if expected_total else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {
        "case_count": len(cases),
        "case_non_cjk_stripped": non_cjk_cases,
        "case_exact_accuracy": round(exact / len(cases), 6),
        "case_boundary_precision": round(precision, 6),
        "case_boundary_recall": round(recall, 6),
        "case_boundary_f1": round(f1, 6),
    }


def _metrics(
    rows: list[dict[str, str]],
    hsk_words: dict[str, int],
    mode: Mode,
    cases: list[dict[str, str]],
    baselines: dict[bool, list[list[str]]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    vocabulary = set(hsk_words) if mode.use_hsk else None
    token_count = 0
    single_count = 0
    matched_count = 0
    level_counts: Counter[int] = Counter()
    unique_tokens: set[str] = set()
    boundary_changes: list[dict[str, object]] = []
    truncated_changes = 0
    tokenizer = build_tokenizer()

    for index, row in enumerate(rows):
        # A non-HSK mode *is* the baseline for its HMM setting, so re-segmenting
        # the corpus for it would reproduce a list we already hold.
        tokens = (
            segment(
                row.get("text", ""),
                tokenizer=tokenizer,
                hmm=mode.hmm,
                hsk_words=vocabulary,
                strategy=mode.strategy,
            )
            if mode.use_hsk
            else baselines[mode.hmm][index]
        )
        token_count += len(tokens)
        single_count += sum(len(token) == 1 for token in tokens)
        unique_tokens.update(tokens)
        for token in tokens:
            level = hsk_words.get(token)
            if level is not None:
                matched_count += 1
                level_counts[level] += 1
        if not mode.use_hsk:
            continue
        baseline = baselines[mode.hmm][index]
        if baseline == tokens:
            continue
        if len(boundary_changes) >= MAX_BOUNDARY_CHANGES:
            truncated_changes += 1
            continue
        boundary_changes.append(
            {
                "exam_id": row.get("exam_id", ""),
                "source_type": row.get("source_type", ""),
                "baseline_token_count": len(baseline),
                "hsk_token_count": len(tokens),
                "token_delta": len(tokens) - len(baseline),
                "baseline_preview": "|".join(baseline[:40]),
                "hsk_preview": "|".join(tokens[:40]),
            }
        )

    levels_total = sum(level_counts.values())
    summary: dict[str, object] = {
        "mode": mode.name,
        "input_rows": len(rows),
        "token_occurrences": token_count,
        "unique_tokens": len(unique_tokens),
        "single_char_occurrences": single_count,
        "single_char_share": round(single_count / token_count, 6) if token_count else 0,
        "hsk_matched_occurrences": matched_count,
        "hsk_match_rate": round(matched_count / token_count, 6) if token_count else 0,
        "unmatched_occurrences": token_count - matched_count,
        "level_1_share_of_all_tokens": round(level_counts[1] / token_count, 6) if token_count else 0,
        "level_1_share_of_hsk_tokens": round(level_counts[1] / levels_total, 6) if levels_total else 0,
        "boundary_changes_recorded": len(boundary_changes),
        "boundary_changes_truncated": truncated_changes,
    }
    summary.update({f"level_{level}_occurrences": level_counts[level] for level in HSK_LEVELS})
    summary.update(_case_metrics(cases, hsk_words, mode, tokenizer))
    return summary, boundary_changes


def _baseline_segmentations(
    rows: list[dict[str, str]],
    hmm_values: set[bool],
) -> dict[bool, list[list[str]]]:
    """Pre-compute the plain-Jieba segmentation once per HMM setting.

    Every HSK mode diffs against the same baseline, and the baseline modes are
    that segmentation, so this cuts the corpus passes from eight to five.
    """

    tokenizer = build_tokenizer()
    return {
        hmm: [segment(row.get("text", ""), tokenizer=tokenizer, hmm=hmm) for row in rows]
        for hmm in sorted(hmm_values)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Jieba configurations.")
    parser.add_argument("--raw", default="data/raw/raw_extractions.csv")
    parser.add_argument("--wordlist", default="data/processed/hsk_wordlist.csv")
    parser.add_argument("--cases", default="data/validation/segmentation_cases.csv")
    parser.add_argument("--output-dir", default="data/validation/jieba")
    args = parser.parse_args()

    raw_path = _require(
        ROOT / args.raw,
        "run the extraction pipeline first (see README) or pass --raw",
    )
    wordlist_path = _require(
        ROOT / args.wordlist,
        "run `python -m etl.extract_wordlist` first or pass --wordlist",
    )
    rows = _read_raw(raw_path)
    hsk_words = load_hsk_words(wordlist_path)
    cases_path = ROOT / args.cases
    cases = _read_cases(cases_path)
    if not cases:
        print(f"warning: no segmentation cases at {cases_path}; case_* metrics omitted")

    summaries: list[dict[str, object]] = []
    output_dir = ROOT / args.output_dir
    baselines = _baseline_segmentations(rows, {mode.hmm for mode in MODES})
    for mode in MODES:
        summary, changes = _metrics(rows, hsk_words, mode, cases, baselines)
        summaries.append(summary)
        if changes:
            _write_csv(output_dir / f"{mode.name}_boundary_changes.csv", changes)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "summary.csv", summaries)
    with open(output_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summaries, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
