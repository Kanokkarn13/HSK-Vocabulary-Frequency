"""Jieba segmentation, cleaning, and frequency counting."""
import re
import jieba
from collections import Counter


_PUNCT_RE = re.compile(
    r"[^一-鿿]"  # keep only CJK unified ideographs
)


def segment(text: str) -> list[str]:
    words = jieba.lcut(text)
    cleaned = [w for w in words if not _PUNCT_RE.sub("", w) == "" and len(w) >= 1]
    # filter single chars that are likely stopwords/particles (optional: tune per HSK level)
    return [w for w in cleaned if _PUNCT_RE.sub("", w)]


def count_frequencies(texts: dict[str, str]) -> Counter:
    """texts: {filename: raw_text}. Returns combined Counter."""
    total: Counter = Counter()
    for filename, text in texts.items():
        words = segment(text)
        total.update(words)
    return total


def count_per_source(texts: dict[str, str]) -> dict[str, Counter]:
    """Return per-file frequency counters."""
    return {fname: Counter(segment(text)) for fname, text in texts.items()}
