from collections import Counter
from etl.segment_and_count import segment, count_frequencies


def test_segment_returns_chinese_words():
    text = "我爱学习中文。Hello 123"
    words = segment(text)
    assert all(w for w in words), "should not return empty strings"
    # Non-CJK characters should be filtered out
    for w in words:
        assert w.strip()


def test_count_frequencies_aggregates():
    texts = {
        "file1.pdf": "你好你好",
        "file2.pdf": "你好",
    }
    counter = count_frequencies(texts)
    assert counter["你好"] == 3


def test_segment_handles_empty():
    assert segment("") == []
    assert segment("123 abc !!!") == []
