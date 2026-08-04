"""Compare Jieba configurations on the project's raw extraction snapshot.

This is a diagnostic experiment. It does not overwrite word_counts.parquet.
Run from the repository root:

    python scripts/evaluate_jieba.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from etl.tokenizer import build_tokenizer, load_hsk_words, segment


ROOT = Path(__file__).resolve().parents[1]


def _read_raw(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_cases(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _case_metrics(
    cases: list[dict[str, str]],
    hsk_words: dict[str, int],
    mode: str,
) -> dict[str, object]:
    if not cases:
        return {}
    use_hmm = mode.endswith("hmm_true")
    use_dp = mode.startswith("hsk_dp")
    use_hsk = mode.startswith("hsk_")
    vocabulary = set(hsk_words) if use_hsk else None
    tokenizer = build_tokenizer()
    exact = 0
    true_positive = predicted_total = expected_total = 0
    for case in cases:
        text = case["text"]
        expected = case["expected_tokens"].split("|")
        predicted = segment(
            text,
            tokenizer=tokenizer,
            hmm=use_hmm,
            hsk_words=vocabulary,
            strategy="dp" if use_dp else "merge",
        )
        exact += predicted == expected
        expected_boundaries = set()
        predicted_boundaries = set()
        cursor = 0
        for token in expected[:-1]:
            cursor += len(token)
            expected_boundaries.add(cursor)
        cursor = 0
        for token in predicted[:-1]:
            cursor += len(token)
            predicted_boundaries.add(cursor)
        true_positive += len(expected_boundaries & predicted_boundaries)
        expected_total += len(expected_boundaries)
        predicted_total += len(predicted_boundaries)
    precision = true_positive / predicted_total if predicted_total else 0
    recall = true_positive / expected_total if expected_total else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {
        "case_count": len(cases),
        "case_exact_accuracy": round(exact / len(cases), 6),
        "case_boundary_precision": round(precision, 6),
        "case_boundary_recall": round(recall, 6),
        "case_boundary_f1": round(f1, 6),
    }


def _metrics(
    rows: list[dict[str, str]],
    hsk_words: dict[str, int],
    mode: str,
    cases: list[dict[str, str]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    use_hmm = mode.endswith("hmm_true")
    use_merge = mode.startswith("hsk_merge")
    use_dp = mode.startswith("hsk_dp")
    vocabulary = set(hsk_words) if (use_merge or use_dp) else None
    token_count = 0
    single_count = 0
    matched_count = 0
    level_counts: Counter[int] = Counter()
    unique_tokens: set[str] = set()
    boundary_changes: list[dict[str, object]] = []
    tokenizer = build_tokenizer()

    for row in rows:
        tokens = segment(
            row.get("text", ""),
            tokenizer=tokenizer,
            hmm=use_hmm,
            hsk_words=vocabulary,
            strategy="dp" if use_dp else "merge",
        )
        token_count += len(tokens)
        single_count += sum(len(token) == 1 for token in tokens)
        unique_tokens.update(tokens)
        for token in tokens:
            level = hsk_words.get(token)
            if level is not None:
                matched_count += 1
                level_counts[level] += 1
        if use_merge or use_dp:
            baseline = segment(row.get("text", ""), tokenizer=tokenizer, hmm=use_hmm)
            if baseline != tokens and len(boundary_changes) < 5000:
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
        "mode": mode,
        "input_rows": len(rows),
        "token_occurrences": token_count,
        "unique_tokens": len(unique_tokens),
        "single_char_occurrences": single_count,
        "single_char_share": round(single_count / token_count, 6) if token_count else 0,
        "hsk_matched_occurrences": matched_count,
        "hsk_match_rate": round(matched_count / token_count, 6) if token_count else 0,
        "unmatched_occurrences": token_count - matched_count,
        "level_1_occurrences": level_counts[1],
        "level_1_share_of_all_tokens": round(level_counts[1] / token_count, 6) if token_count else 0,
        "level_1_share_of_hsk_tokens": round(level_counts[1] / levels_total, 6) if levels_total else 0,
    }
    summary.update({f"level_{level}_occurrences": level_counts[level] for level in range(1, 10) if level_counts[level]})
    summary.update(_case_metrics(cases, hsk_words, mode))
    return summary, boundary_changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/raw_extractions.csv")
    parser.add_argument("--wordlist", default="data/processed/hsk_wordlist.csv")
    parser.add_argument("--cases", default="data/validation/segmentation_cases.csv")
    parser.add_argument("--output-dir", default="data/validation/jieba")
    args = parser.parse_args()

    rows = _read_raw(ROOT / args.raw)
    hsk_words = load_hsk_words(ROOT / args.wordlist)
    cases = _read_cases(ROOT / args.cases)
    modes = [
        "baseline_hmm_true",
        "baseline_hmm_false",
        "hsk_merge_hmm_true",
        "hsk_merge_hmm_false",
        "hsk_dp_hmm_true",
    ]
    summaries: list[dict[str, object]] = []
    output_dir = ROOT / args.output_dir
    for mode in modes:
        summary, changes = _metrics(rows, hsk_words, mode, cases)
        summaries.append(summary)
        if changes:
            _write_csv(output_dir / f"{mode}_boundary_changes.csv", changes)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "summary.csv", summaries)
    with open(output_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summaries, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
