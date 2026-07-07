from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import BROWSER_HEADERS

client = TestClient(app)


def get(path: str):
    return client.get(path, headers=BROWSER_HEADERS)


def test_compare_default_splits_by_official_wordlist(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["word"] for r in body["not_in_official_wordlist"]] == ["喵星人"]
    assert [r["word"] for r in body["in_official_wordlist"]] == ["你好", "因为", "谢谢"]


def test_compare_filters_by_hsk_level(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual?hsk_level=1")
    body = resp.json()
    assert {r["word"] for r in body["in_official_wordlist"]} == {"你好", "谢谢"}
    # 喵星人 has no hsk_level at all, so an hsk_level=1 filter excludes it
    assert body["not_in_official_wordlist"] == []


def test_compare_scoped_to_one_exam(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual?exam_id=2021-02")
    body = resp.json()
    in_wl = {r["word"]: r["total_frequency"] for r in body["in_official_wordlist"]}
    assert in_wl == {"因为": 10, "你好": 2}
    assert [r["word"] for r in body["not_in_official_wordlist"]] == ["喵星人"]


def test_compare_scoped_to_exam_level_aggregates_across_reading_and_listening(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual?exam_level=3")
    body = resp.json()
    in_wl = {r["word"]: r["total_frequency"] for r in body["in_official_wordlist"]}
    assert in_wl == {"你好": 8, "谢谢": 1}
    assert body["not_in_official_wordlist"] == []  # 喵星人 only appears in the HSK4 exam


def test_compare_exam_level_with_source_type_filter(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual?exam_level=3&source_type=reading")
    body = resp.json()
    in_wl = {r["word"]: r["total_frequency"] for r in body["in_official_wordlist"]}
    assert in_wl == {"你好": 5, "谢谢": 1}


def test_compare_empty_when_nothing_matches(seeded_db):
    resp = get("/api/compare/wordlist-vs-actual?hsk_level=6")
    body = resp.json()
    assert body["in_official_wordlist"] == []
    assert body["not_in_official_wordlist"] == []
