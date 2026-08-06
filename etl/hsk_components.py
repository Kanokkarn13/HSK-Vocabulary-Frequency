"""Map Jieba tokens to HSK vocabulary components.

This module deliberately separates tokenisation from HSK attribution. A
non-HSK Jieba token is decomposed only when the whole token can be covered by
HSK words and at least one component has two or more characters. That guard
prevents OCR/ASR noise from becoming a pile of level-1 single characters.
"""

from __future__ import annotations

from collections.abc import Mapping
from collections import Counter


_SURNAME_CHARS = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡林郭何高罗郑梁谢宋唐许邓冯韩曹彭曾萧田董袁潘于蒋蔡余杜叶"
    "程苏魏吕丁沈任姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾"
    "毛郝龚邵万钱严覃武戴莫孔向汤"
)
_NAME_TAILS = {"先生", "小姐", "老师", "医生", "经理"}


def _is_decomposable_token(token: str, vocabulary: set[str], max_word_chars: int) -> bool:
    if not token or max_word_chars < 2 or token in vocabulary:
        return False
    if token[0] in _SURNAME_CHARS and token[1:] in _NAME_TAILS:
        return False
    return len(token) >= 2 and all("\u4e00" <= char <= "\u9fff" for char in token)


def _candidate_words(token: str, vocabulary: set[str], max_word_chars: int) -> list[list[str]]:
    candidates: list[list[str]] = [[] for _ in range(len(token) + 1)]
    for start in range(len(token)):
        for end in range(start + 1, min(len(token), start + max_word_chars) + 1):
            part = token[start:end]
            if part in vocabulary:
                candidates[start].append(part)
    return candidates


def _extend_score(
    state: tuple[int, int, int, list[str]],
    part: str,
) -> tuple[int, int, int, list[str]]:
    return (
        state[0] + int(len(part) >= 2),
        state[1] + len(part) ** 2,
        state[2] - 1,
        state[3] + [part],
    )


def _best_component_path(token: str, vocabulary: set[str], max_word_chars: int) -> list[str] | None:
    best: list[tuple[int, int, int, list[str]] | None] = [None] * (len(token) + 1)
    best[0] = (0, 0, 0, [])
    candidates = _candidate_words(token, vocabulary, max_word_chars)
    for start in range(len(token)):
        state = best[start]
        if state is None:
            continue
        for part in candidates[start]:
            end = start + len(part)
            candidate = _extend_score(state, part)
            current = best[end]
            if current is None or candidate[:3] > current[:3]:
                best[end] = candidate
    result = best[-1]
    if result is None or not any(len(part) >= 2 for part in result[3]):
        return None
    return result[3]


def resolve_components(
    token: str,
    hsk_words: Mapping[str, int] | set[str],
    *,
    max_word_chars: int = 4,
) -> list[str] | None:
    """Return HSK components for ``token`` or ``None`` when unsafe.

    Direct HSK words return a one-item list. For decomposition, candidates are
    scored by (1) using a multi-character HSK word, (2) longer components, and
    (3) fewer components. A decomposition made only of single characters is
    rejected on purpose.
    """

    if not token or max_word_chars < 2:
        return None
    vocabulary = set(hsk_words)
    if token in vocabulary:
        return [token]
    if not _is_decomposable_token(token, vocabulary, max_word_chars):
        return None
    return _best_component_path(token, vocabulary, max_word_chars)


def component_levels(
    token: str,
    hsk_words: Mapping[str, int],
    *,
    max_word_chars: int = 4,
) -> tuple[list[str] | None, list[int] | None, str]:
    """Return components, their HSK levels, and ``direct/decomposed/unmatched``."""

    if token in hsk_words:
        return [token], [hsk_words[token]], "direct"
    components = resolve_components(token, hsk_words, max_word_chars=max_word_chars)
    if components is None:
        return None, None, "unmatched"
    return components, [hsk_words[word] for word in components], "decomposed"


def attribute_counter(
    counts: Counter[str],
    hsk_words: Mapping[str, int],
    *,
    max_word_chars: int = 4,
) -> Counter[str]:
    """Convert raw token counts into HSK-attributed counts.

    Direct words remain unchanged. Safely decomposed tokens contribute their
    count to each component. Unmatched tokens remain visible for later review.
    """

    attributed: Counter[str] = Counter()
    for token, count in counts.items():
        components, _, _ = component_levels(token, hsk_words, max_word_chars=max_word_chars)
        for component in components or [token]:
            attributed[component] += count
    return attributed


__all__ = ["attribute_counter", "component_levels", "resolve_components"]
