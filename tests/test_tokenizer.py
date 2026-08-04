from etl.tokenizer import build_tokenizer, segment
from etl.hsk_components import attribute_counter, component_levels, resolve_components


def test_baseline_does_not_drop_cjk_tokens():
    assert segment("我爱学习中文。Hello 123")
    assert all(token and all("\u4e00" <= char <= "\u9fff" for char in token) for token in segment("我爱学习中文。Hello 123"))


def test_hsk_vocabulary_repairs_split_boundary():
    tokens = segment(
        "我在图书馆学习",
        tokenizer=build_tokenizer(),
        hsk_words={"图书馆"},
    )
    assert "图书馆" in tokens


def test_hsk_merge_does_not_cross_punctuation():
    tokens = segment(
        "图。书馆",
        tokenizer=build_tokenizer(),
        hsk_words={"图书馆"},
    )
    assert tokens == ["图", "书馆"]


def test_hsk_merge_prefers_longest_local_word():
    tokens = segment(
        "我有一点时间",
        tokenizer=build_tokenizer(),
        hsk_words={"一点", "有一点"},
    )
    assert "有一点" in tokens


def test_hmm_can_be_selected_without_changing_api():
    assert segment("你好", tokenizer=build_tokenizer(), hmm=False)


def test_dp_strategy_uses_hsk_word_over_single_char_candidates():
    tokens = segment(
        "我觉得这个问题很重要",
        tokenizer=build_tokenizer(),
        hsk_words={"我", "觉得", "这个", "问题", "很", "重要"},
        strategy="dp",
    )
    assert tokens == ["我", "觉得", "这个", "问题", "很", "重要"]


def test_invalid_strategy_is_rejected():
    try:
        segment("你好", strategy="unknown")
    except ValueError as exc:
        assert "strategy" in str(exc)
    else:
        raise AssertionError("invalid strategy should fail")


def test_hsk_components_decompose_non_hsk_token():
    vocab = {"做": 1, "作业": 2, "谢谢": 1, "您": 1}
    assert resolve_components("做作业", vocab) == ["做", "作业"]
    assert component_levels("谢谢您", vocab) == (["谢谢", "您"], [1, 1], "decomposed")


def test_hsk_components_reject_single_character_only_decomposition():
    assert resolve_components("这是", {"这": 1, "是": 1}) is None
    assert component_levels("这是", {"这": 1, "是": 1}) == (None, None, "unmatched")


def test_hsk_components_do_not_split_common_surname_title():
    assert resolve_components("王先生", {"王": 1, "先生": 1}) is None


def test_attribute_counter_preserves_unmatched_and_expands_components():
    counts = attribute_counter(
        {"做作业": 2, "图书馆": 3, "王先生": 4},
        {"做": 1, "作业": 2, "图书馆": 2, "王": 1, "先生": 1},
    )
    assert counts["做"] == 2
    assert counts["作业"] == 2
    assert counts["图书馆"] == 3
    assert counts["王先生"] == 4
