"""Jieba segmentation, cleaning, and frequency counting."""
from collections import Counter
from etl.tokenizer import DEFAULT_HMM, DEFAULT_STRATEGY, segment as segment_text


def segment(
    text: str,
    *,
    hsk_words: set[str] | None = None,
    hmm: bool = DEFAULT_HMM,
    strategy: str = DEFAULT_STRATEGY,
) -> list[str]:
    """Return CJK tokens, with optional HSK-aware boundary repair.

    The default remains the old Jieba baseline.  Pass ``hsk_words`` only after
    reviewing the tokenizer experiment report.
    """

    return segment_text(text, hmm=hmm, hsk_words=hsk_words, strategy=strategy)


def count_frequencies(
    texts: dict[str, str],
    *,
    hsk_words: set[str] | None = None,
    hmm: bool = DEFAULT_HMM,
    strategy: str = DEFAULT_STRATEGY,
) -> Counter:
    """texts: {filename: raw_text}. Returns combined Counter."""
    total: Counter = Counter()
    for filename, text in texts.items():
        words = segment(text, hsk_words=hsk_words, hmm=hmm, strategy=strategy)
        total.update(words)
    return total


def count_per_source(
    texts: dict[str, str],
    *,
    hsk_words: set[str] | None = None,
    hmm: bool = DEFAULT_HMM,
    strategy: str = DEFAULT_STRATEGY,
) -> dict[str, Counter]:
    """Return per-file frequency counters."""
    return {
        fname: Counter(segment(text, hsk_words=hsk_words, hmm=hmm, strategy=strategy))
        for fname, text in texts.items()
    }
