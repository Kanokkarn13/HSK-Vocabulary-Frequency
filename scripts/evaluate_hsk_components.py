"""Evaluate HSK component attribution without changing existing outputs.

Run from repository root:

    python -m scripts.evaluate_hsk_components

Required inputs:

    data/processed/word_counts.csv      tracked; produced by the ETL pipeline
    data/processed/hsk_wordlist.csv     gitignored; `python -m etl.extract_wordlist`

"Newly attributed" is measured against the match_type already recorded in
word_counts.csv, so the headline numbers describe the delta between the current
etl.hsk_components logic and whatever produced that snapshot.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from etl.hsk_components import component_levels
from etl.tokenizer import load_hsk_words


ROOT = Path(__file__).resolve().parents[1]


def _require(path: Path, hint: str) -> Path:
    """Fail with an actionable message instead of a bare FileNotFoundError."""

    if not path.exists():
        raise SystemExit(f"missing required input: {path}\n  {hint}")
    return path


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


TOKEN_FIELDNAMES = [
    "raw_token",
    "occurrences",
    "components",
    "component_levels",
    "match_type",
    "original_match_type",
    "newly_attributed",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate HSK component attribution.")
    parser.add_argument("--counts", default="data/processed/word_counts.csv")
    parser.add_argument("--wordlist", default="data/processed/hsk_wordlist.csv")
    parser.add_argument("--output-dir", default="data/validation/hsk_components")
    args = parser.parse_args()

    counts_path = _require(
        ROOT / args.counts,
        "run the ETL pipeline first (see README) or pass --counts",
    )
    wordlist_path = _require(
        ROOT / args.wordlist,
        "run `python -m etl.extract_wordlist` first or pass --wordlist",
    )

    words = load_hsk_words(wordlist_path)
    totals: Counter[str] = Counter()
    original_types: dict[str, set[str]] = defaultdict(set)
    component_totals: Counter[str] = Counter()
    component_levels_map: dict[str, set[int]] = defaultdict(set)
    rows: list[dict[str, object]] = []
    decomposed_tokens = 0
    decomposed_occurrences = 0
    with open(counts_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            token = row["word"]
            count = int(row["count"])
            totals[token] += count
            original_types[token].add(row["match_type"])

    for token, count in totals.items():
        components, levels, match_type = component_levels(token, words)
        newly_attributed = "unmatched" in original_types[token] and match_type == "decomposed"
        if newly_attributed:
            decomposed_tokens += 1
            decomposed_occurrences += count
        if newly_attributed and components and levels:
            for component, level in zip(components, levels):
                component_totals[component] += count
                component_levels_map[component].add(level)
        rows.append(
            {
                "raw_token": token,
                "occurrences": count,
                "components": "|".join(components or []),
                "component_levels": "|".join(str(level) for level in (levels or [])),
                "match_type": match_type,
                "original_match_type": "|".join(sorted(original_types[token])),
                "newly_attributed": newly_attributed,
            }
        )

    output_dir = ROOT / args.output_dir
    # Fieldnames are declared rather than read off rows[0], so an empty
    # word_counts.csv still writes a valid header instead of raising IndexError.
    _write_csv(output_dir / "token_attribution.csv", rows, TOKEN_FIELDNAMES)
    _write_csv(
        output_dir / "component_frequency.csv",
        [
            {
                "word": word,
                "occurrences": count,
                "levels": "|".join(map(str, sorted(component_levels_map[word]))),
            }
            for word, count in component_totals.most_common()
        ],
        ["word", "occurrences", "levels"],
    )

    print(f"Unique raw tokens: {len(rows)}")
    print(f"Safely decomposed tokens: {decomposed_tokens}")
    print(f"Safely decomposed occurrences: {decomposed_occurrences}")
    print(f"Component vocabulary rows: {len(component_totals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
