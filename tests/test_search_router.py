from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import BROWSER_HEADERS

client = TestClient(app)


def get(path: str):
    return client.get(path, headers=BROWSER_HEADERS)


def test_search_word_orders_occurrences_by_frequency_desc(seeded_db):
    resp = get("/api/search/word?q=你好")
    assert resp.status_code == 200
    body = resp.json()
    freqs = [row["frequency"] for row in body["occurrences"]]
    assert freqs == [5, 3, 2]
    assert {row["source_type"] for row in body["occurrences"]} == {"reading", "listening"}
    assert len(body["aggregates"]) == 3  # reading, listening, all


def test_search_word_joins_exam_filename(seeded_db):
    resp = get("/api/search/word?q=谢谢")
    body = resp.json()
    assert body["occurrences"][0]["filename"] == "reading_2020_01.pdf"
    assert body["occurrences"][0]["year"] == 2020


def test_search_word_not_found_returns_empty_lists(seeded_db):
    resp = get("/api/search/word?q=不存在")
    assert resp.status_code == 200
    body = resp.json()
    assert body["occurrences"] == []
    assert body["aggregates"] == []


def test_search_word_rejects_empty_query(seeded_db):
    resp = get("/api/search/word?q=")
    assert resp.status_code == 422


def test_search_word_rejects_overlong_query(seeded_db):
    resp = get("/api/search/word?q=" + "x" * 51)
    assert resp.status_code == 422


def test_word_detail_returns_definitions_and_examples(seeded_db):
    resp = get("/api/search/word-detail?q=你好")
    assert resp.status_code == 200
    body = resp.json()
    assert body["in_wordlist"] is True
    assert body["pinyin"] == "nǐ hǎo"
    assert body["definition"] == "hello"
    assert body["definition_th"] == "สวัสดี"
    assert body["sentence_total"] == 2
    assert body["file_total"] == 2
    filenames = {s["filename"] for s in body["sentences"]}
    assert filenames == {"reading_2020_01.pdf", "listening_2020_01.mp3"}


def test_word_detail_dedupes_repeated_sentence_within_one_file(seeded_db):
    """'你好你好，请问现在几点了？' contains 你好 twice but is one sentence row --
    sentence_total counts distinct sentence text, not occurrence count."""
    resp = get("/api/search/word-detail?q=你好")
    body = resp.json()
    listening_sentences = [s["sentence"] for s in body["sentences"] if s["source_type"] == "listening"]
    assert listening_sentences == ["你好你好，请问现在几点了？"]


def test_word_detail_unknown_word_has_no_definition_or_examples(seeded_db):
    resp = get("/api/search/word-detail?q=喵星人")
    body = resp.json()
    assert body["in_wordlist"] is False
    assert body["pinyin"] is None
    assert body["definition"] is None
    assert body["sentence_total"] == 0
    assert body["file_total"] == 0
    assert body["sentences"] == []


def test_word_detail_matches_word_within_longer_sentence(seeded_db):
    resp = get("/api/search/word-detail?q=因为")
    body = resp.json()
    assert body["definition"] == "because"
    assert body["sentence_total"] == 1
    assert body["sentences"][0]["exam_hsk_level"] == 4


def test_word_detail_rejects_empty_query(seeded_db):
    resp = get("/api/search/word-detail?q=")
    assert resp.status_code == 422
