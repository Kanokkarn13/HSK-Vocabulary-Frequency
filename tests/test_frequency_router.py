from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import BROWSER_HEADERS

client = TestClient(app)


def get(path: str):
    return client.get(path, headers=BROWSER_HEADERS)


def test_exams_groups_reading_and_listening_into_one_entry(seeded_db):
    resp = get("/api/frequency/exams")
    assert resp.status_code == 200
    body = resp.json()
    by_id = {row["exam_id"]: row for row in body["items"]}
    assert body["count"] == 2
    assert by_id["2020-01"]["hsk_level"] == 3
    assert by_id["2020-01"]["source_types"] == ["listening", "reading"]
    assert by_id["2021-02"]["hsk_level"] == 4
    assert by_id["2021-02"]["source_types"] == ["reading"]


def test_top_default_uses_all_source_aggregate(seeded_db):
    resp = get("/api/frequency/top")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 4
    words = [row["word"] for row in body["items"]]
    # Descending by total_frequency: 你好(10), 因为(8), then the two 1s in any order
    assert words[0] == "你好"
    assert words[1] == "因为"
    assert set(words[2:]) == {"谢谢", "喵星人"}


def test_top_filters_by_hsk_level(seeded_db):
    resp = get("/api/frequency/top?hsk_level=1")
    body = resp.json()
    assert body["total_count"] == 2
    assert {row["word"] for row in body["items"]} == {"你好", "谢谢"}


def test_top_filters_by_source_type(seeded_db):
    resp = get("/api/frequency/top?source_type=reading")
    body = resp.json()
    words = {row["word"]: row["total_frequency"] for row in body["items"]}
    assert words == {"你好": 7, "谢谢": 1, "因为": 8, "喵星人": 1}


def test_top_respects_limit(seeded_db):
    resp = get("/api/frequency/top?limit=1")
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["word"] == "你好"
    # total_count still reflects the full match count, not just this page
    assert body["total_count"] == 4


def test_top_scoped_to_exam_level_aggregates_live(seeded_db):
    resp = get("/api/frequency/top?exam_level=3")
    body = resp.json()
    words = {row["word"]: row for row in body["items"]}
    assert words["你好"]["total_frequency"] == 8  # 5 (reading) + 3 (listening)
    assert words["你好"]["exam_count"] == 1
    assert words["你好"]["source_type"] == "all"  # spans reading + listening
    assert words["谢谢"]["source_type"] == "reading"
    assert "因为" not in words  # only appears in the HSK4 exam


def test_top_scoped_to_specific_exam_ids(seeded_db):
    resp = get("/api/frequency/top?exam_id=2021-02")
    body = resp.json()
    words = {row["word"] for row in body["items"]}
    assert words == {"你好", "因为", "喵星人"}


def test_top_exam_id_and_source_type_combine(seeded_db):
    """Regression test: /top used to silently drop source_type whenever
    exam_id/exam_level was set (see filter-UX fix in project history)."""
    resp = get("/api/frequency/top?exam_id=2020-01&source_type=listening")
    body = resp.json()
    words = {row["word"]: row for row in body["items"]}
    assert set(words) == {"你好"}
    assert words["你好"]["total_frequency"] == 3


def test_top_empty_result_when_no_match(seeded_db):
    resp = get("/api/frequency/top?hsk_level=6")
    body = resp.json()
    assert body["items"] == []
    assert body["total_count"] == 0


def test_top_rejects_hsk_level_out_of_range(seeded_db):
    resp = get("/api/frequency/top?hsk_level=10")
    assert resp.status_code == 422


def test_top_rejects_limit_out_of_range(seeded_db):
    assert get("/api/frequency/top?limit=0").status_code == 422
    assert get("/api/frequency/top?limit=10001").status_code == 422
