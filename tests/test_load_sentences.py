from unittest.mock import patch

import pandas as pd
from sqlalchemy import text

from etl.load_sentences import extract_sentences, _clean_candidate, run


def test_extract_sentences_splits_on_terminal_punctuation():
    # Each segment needs >= 6 CJK chars to clear _clean_candidate's length floor
    text_in = "我今天很高兴看到你。你今天心情怎么样呢？我们一起去公园散步吧！"
    sentences = extract_sentences(text_in)
    assert sentences == ["我今天很高兴看到你。", "你今天心情怎么样呢？", "我们一起去公园散步吧！"]


def test_extract_sentences_strips_leading_question_number():
    assert _clean_candidate("12．他每天早上跑步。") == "他每天早上跑步。"
    assert _clean_candidate("１２、他每天早上跑步。") == "他每天早上跑步。"


def test_extract_sentences_strips_leading_cjk_numeral():
    assert _clean_candidate("一，我们明天见面。") == "我们明天见面。"


def test_extract_sentences_strips_leading_option_letter():
    assert _clean_candidate("A 我喜欢吃苹果。") == "我喜欢吃苹果。"


def test_extract_sentences_strips_lian_ru_prefix():
    assert _clean_candidate("例如：他昨天去了图书馆。") == "他昨天去了图书馆。"


def test_extract_sentences_drops_short_candidates():
    assert _clean_candidate("你好。") is None  # only 2 CJK chars, below the 6-char floor


def test_extract_sentences_drops_overlong_candidates():
    long_sentence = "我" * 81
    assert _clean_candidate(long_sentence) is None


def test_extract_sentences_drops_mid_sentence_option_letters():
    assert _clean_candidate("老朋友 B 不认识的字，还有很多问题。") is None


def test_extract_sentences_drops_fill_in_the_blank_items():
    assert _clean_candidate("我（ ）去过北京，但是很想去。") is None


def test_extract_sentences_drops_low_cjk_ratio_lines():
    assert _clean_candidate("HSK Level 3 Reading Test Paper Instructions Booklet") is None


def test_extract_sentences_dedupes_within_one_file():
    text_in = "他每天早上跑步。他每天早上跑步。他每天晚上看书。"
    sentences = extract_sentences(text_in)
    assert sentences == ["他每天早上跑步。", "他每天晚上看书。"]


def test_extract_sentences_splits_on_newline_too():
    """Reading PDFs put one item per line with no terminal punctuation --
    newlines must split candidates independently of punctuation."""
    text_in = "他每天早上跑步\n他每天晚上都在看书。"
    sentences = extract_sentences(text_in)
    assert sentences == ["他每天早上跑步", "他每天晚上都在看书。"]


def test_run_loads_cleaned_sentences_and_drops_boilerplate(db_session, tmp_path, monkeypatch):
    """End-to-end: parquet -> cleaned/deduped sentences -> exam_sentences table,
    with cross-exam boilerplate (repeated in >=3 exams) filtered out."""
    boilerplate = "请仔细阅读下面的题目和要求。"  # appears in 3 exams -> should be dropped
    df = pd.DataFrame(
        [
            {"exam_id": "e1", "source_type": "reading", "text": f"{boilerplate}他每天早上跑步。"},
            {"exam_id": "e2", "source_type": "reading", "text": f"{boilerplate}他喜欢喝茶不喜欢喝咖啡。"},
            {"exam_id": "e3", "source_type": "reading", "text": f"{boilerplate}我们明天一起去看电影。"},
        ]
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    df.to_parquet(raw_dir / "raw_extractions.parquet")

    # exam_sources rows are required by exam_sentences' FK constraint
    for exam_id in ("e1", "e2", "e3"):
        db_session.execute(
            text("""
                INSERT INTO exam_sources (exam_id, source_type, year, hsk_level, filename)
                VALUES (:exam_id, 'reading', 2020, 3, :filename)
            """),
            {"exam_id": exam_id, "filename": f"{exam_id}.pdf"},
        )
    db_session.commit()

    with patch("etl.load_sentences.DATA_DIR", tmp_path), \
         patch("etl.load_sentences.get_engine", return_value=db_session.get_bind()):
        run()

    sentences = db_session.execute(text("SELECT sentence FROM exam_sentences ORDER BY sentence")).scalars().all()
    assert boilerplate not in sentences
    assert "他每天早上跑步。" in sentences
    assert "他喜欢喝茶不喜欢喝咖啡。" in sentences
    assert "我们明天一起去看电影。" in sentences
    assert len(sentences) == 3
