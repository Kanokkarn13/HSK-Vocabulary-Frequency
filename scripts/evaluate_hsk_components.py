"""Evaluate HSK component attribution without changing existing outputs.

Run from repository root:

    python -m scripts.evaluate_hsk_components
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from etl.hsk_components import component_levels
from etl.tokenizer import load_hsk_words


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    words = load_hsk_words(ROOT / "data/processed/hsk_wordlist.csv")
    totals: Counter[str] = Counter()
    original_types: dict[str, set[str]] = defaultdict(set)
    component_totals: Counter[str] = Counter()
    component_levels_map: dict[str, set[int]] = defaultdict(set)
    rows: list[dict[str, object]] = []
    with open(ROOT / "data/processed/word_counts.csv", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            token = row["word"]
            count = int(row["count"])
            totals[token] += count
            original_types[token].add(row["match_type"])

    for token, count in totals.items():
        components, levels, match_type = component_levels(token, words)
        newly_attributed = "unmatched" in original_types[token] and match_type == "decomposed"
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

    output_dir = ROOT / "data/validation/hsk_components"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "token_attribution.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(output_dir / "component_frequency.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["word", "occurrences", "levels"])
        writer.writeheader()
        for word, count in component_totals.most_common():
            writer.writerow({"word": word, "occurrences": count, "levels": "|".join(map(str, sorted(component_levels_map[word])))})

    decomposed_tokens = sum(row["newly_attributed"] for row in rows)
    decomposed_occurrences = sum(row["occurrences"] for row in rows if row["newly_attributed"])
    print(f"Unique raw tokens: {len(rows)}")
    print(f"Safely decomposed tokens: {decomposed_tokens}")
    print(f"Safely decomposed occurrences: {decomposed_occurrences}")
    print(f"Component vocabulary rows: {len(component_totals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
