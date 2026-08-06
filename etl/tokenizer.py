"""Project-local Jieba tokenizer with optional HSK-aware boundary repair.

Jieba is still the first-pass segmenter.  The HSK vocabulary is used only to
repair boundaries that Jieba split too aggressively (for example ``图`` +
``书馆`` -> ``图书馆``).  It is deliberately not loaded wholesale into Jieba
with a very high frequency because that can change unrelated boundaries.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

import jieba


_NON_CJK_RE = re.compile(r"[^\u4e00-\u9fff]")

# Single source of truth for the production configuration.  Experiments may
# override these arguments explicitly, but Notebook/CLI/Airflow should import
# these constants instead of silently drifting apart.
DEFAULT_HMM = True
DEFAULT_STRATEGY = "merge"
DEFAULT_MAX_HSK_CHARS = 4


def load_hsk_words(csv_path: str | Path) -> dict[str, int]:
    """Load ``word -> level`` from the project's HSK CSV snapshot."""

    words: dict[str, int] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            word = (row.get("word") or "").strip()
            raw_level = (row.get("level") or row.get("hsk_level") or "").strip()
            if not word or not raw_level:
                continue
            try:
                level = int(float(raw_level))
            except ValueError:
                continue
            if 1 <= level <= 9 and not _NON_CJK_RE.search(word):
                words[word] = level
    return words


def build_tokenizer() -> jieba.Tokenizer:
    """Return an isolated Jieba tokenizer for deterministic tests and runs."""

    return jieba.Tokenizer()


_DEFAULT_TOKENIZER = build_tokenizer()


def _is_cjk_token(token: str) -> bool:
    return bool(token) and not _NON_CJK_RE.search(token)


def _merge_hsk_boundaries(
    tokens: list[str],
    hsk_words: set[str],
    max_chars: int,
) -> list[str]:
    """Merge adjacent Jieba tokens only when their concatenation is HSK.

    Longest-match is applied within a short local window.  Punctuation and
    non-CJK tokens are not passed to this function, so they remain boundaries
    in the caller and cannot accidentally join text from two sentences.
    """

    if not hsk_words or not tokens:
        return tokens

    result: list[str] = []
    index = 0
    while index < len(tokens):
        best: str | None = None
        best_end = index + 1
        joined = ""
        for end in range(index, min(len(tokens), index + max_chars)):
            joined += tokens[end]
            if len(joined) >= 2 and joined in hsk_words:
                best = joined
                best_end = end + 1
        result.append(best if best is not None else tokens[index])
        index = best_end
    return result


def _index_baseline_tokens(tokens: list[str]) -> dict[int, list[str]]:
    indexed: dict[int, list[str]] = {}
    cursor = 0
    for token in tokens:
        indexed.setdefault(cursor, []).append(token)
        cursor += len(token)
    return indexed


def _index_hsk_words(text: str, hsk_words: set[str], max_word_chars: int) -> dict[int, list[str]]:
    indexed: dict[int, list[str]] = {}
    for start in range(len(text)):
        for end in range(start + 2, min(len(text), start + max_word_chars) + 1):
            candidate = text[start:end]
            if candidate in hsk_words:
                indexed.setdefault(start, []).append(candidate)
    return indexed


def _candidate_score(
    current: tuple[int, int, int, int, int],
    candidate: str,
    hsk_words: set[str],
    baseline_candidates: set[str],
) -> tuple[int, int, int, int, int]:
    is_baseline_single = len(candidate) == 1 and candidate in baseline_candidates
    is_hsk = candidate in hsk_words and (len(candidate) >= 2 or is_baseline_single)
    return (
        current[0] + (len(candidate) if is_hsk else 0),
        current[1] + (len(candidate) ** 2 if is_hsk else 0),
        current[2] - (0 if is_hsk else len(candidate)),
        current[3] - 1,
        current[4] + (len(candidate) if candidate in baseline_candidates else 0),
    )


def _dp_segment_run(
    text: str,
    baseline_tokens: list[str],
    hsk_words: set[str],
    max_word_chars: int,
) -> list[str]:
    """Choose a segmentation for one CJK run with a small word lattice.

    Multi-character HSK words and baseline Jieba tokens are candidates.
    Selection is lexicographic: maximise HSK-covered characters, prefer longer
    HSK entries, minimise unmatched characters, then prefer fewer/Jieba-
    compatible tokens. A single character receives HSK credit only when Jieba
    already emitted it as a standalone token; this prevents pathological
    splitting of every unknown compound into level-1 characters.
    """

    baseline_by_start = _index_baseline_tokens(baseline_tokens)
    hsk_by_start = _index_hsk_words(text, hsk_words, max_word_chars)

    # (HSK chars, long-HSK preference, -unmatched chars, -token count,
    #  Jieba-compatible chars)
    unreachable = (-1, -1, -len(text) - 1, -len(text) - 1, -1)
    best_score = [unreachable] * (len(text) + 1)
    best_tokens: list[list[str]] = [[] for _ in range(len(text) + 1)]
    best_score[0] = (0, 0, 0, 0, 0)

    for start in range(len(text)):
        if best_score[start] == unreachable:
            continue
        baseline_candidates = set(baseline_by_start.get(start, []))
        candidates = set(hsk_by_start.get(start, [])) | baseline_candidates | {text[start]}
        current = best_score[start]
        for candidate in candidates:
            end = start + len(candidate)
            score = _candidate_score(current, candidate, hsk_words, baseline_candidates)
            if score > best_score[end]:
                best_score[end] = score
                best_tokens[end] = best_tokens[start] + [candidate]
    return best_tokens[-1]


def _dp_segment(
    tokens: list[str],
    hsk_words: set[str],
    max_word_chars: int,
) -> list[str]:
    result: list[str] = []
    run: list[str] = []
    for token in tokens:
        if _is_cjk_token(token):
            run.append(token)
            continue
        if run:
            text = "".join(run)
            result.extend(_dp_segment_run(text, run, hsk_words, max_word_chars))
            run.clear()
    if run:
        text = "".join(run)
        result.extend(_dp_segment_run(text, run, hsk_words, max_word_chars))
    return result


def segment(
    text: str,
    *,
    tokenizer: jieba.Tokenizer | None = None,
    hmm: bool = DEFAULT_HMM,
    hsk_words: Iterable[str] | None = None,
    max_hsk_chars: int = DEFAULT_MAX_HSK_CHARS,
    strategy: str = DEFAULT_STRATEGY,
) -> list[str]:
    """Segment Chinese text, optionally repairing boundaries with HSK words.

    ``hsk_words`` is opt-in so existing callers keep the old Jieba baseline.
    The future production configuration should pass the HSK snapshot here
    after the experiment report has been reviewed.
    """

    if not text:
        return []
    if max_hsk_chars < 2:
        raise ValueError("max_hsk_chars must be at least 2")
    if strategy not in {"merge", "dp"}:
        raise ValueError("strategy must be 'merge' or 'dp'")

    tok = tokenizer or _DEFAULT_TOKENIZER
    vocabulary = set(hsk_words or ())
    result: list[str] = []
    cjk_run: list[str] = []

    def flush() -> None:
        if cjk_run:
            if strategy == "dp":
                result.extend(_dp_segment(cjk_run, vocabulary, max_hsk_chars))
            else:
                result.extend(_merge_hsk_boundaries(cjk_run, vocabulary, max_hsk_chars))
            cjk_run.clear()

    for token in tok.lcut(text, HMM=hmm):
        if _is_cjk_token(token):
            cjk_run.append(token)
        else:
            flush()
    flush()
    return result


__all__ = [
    "DEFAULT_HMM",
    "DEFAULT_MAX_HSK_CHARS",
    "DEFAULT_STRATEGY",
    "build_tokenizer",
    "load_hsk_words",
    "segment",
]
