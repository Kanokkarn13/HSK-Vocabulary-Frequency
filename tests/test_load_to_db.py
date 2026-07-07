from collections import Counter

from sqlalchemy import text

from etl.load_to_db import (
    load_frequencies,
    load_wordlist_csv,
    refresh_aggregates,
    upsert_exam_source,
)


def _write_csv(tmp_path, rows: list[dict]):
    import csv

    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "wordlist.csv"
    fieldnames = ["word", "pinyin", "hsk_level", "definition", "definition_th"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def test_load_wordlist_csv_inserts_rows(db_session, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            {"word": "你好", "pinyin": "nǐ hǎo", "hsk_level": "1", "definition": "hello", "definition_th": "สวัสดี"},
            {"word": "谢谢", "pinyin": "xiè xie", "hsk_level": "1", "definition": "", "definition_th": ""},
        ],
    )
    words = load_wordlist_csv(csv_path, db_session)
    assert words == {"你好", "谢谢"}
    row = db_session.execute(
        text("SELECT pinyin, hsk_level, definition FROM hsk_wordlist WHERE word = '你好'")
    ).mappings().one()
    assert row["pinyin"] == "nǐ hǎo"
    assert row["hsk_level"] == 1
    assert row["definition"] == "hello"
    # blank definition string is stored as NULL, not ""
    blank = db_session.execute(
        text("SELECT definition FROM hsk_wordlist WHERE word = '谢谢'")
    ).scalar_one()
    assert blank is None


def test_load_wordlist_csv_skips_bad_level_rows(db_session, tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            {"word": "你好", "pinyin": "nǐ hǎo", "hsk_level": "1", "definition": "hello", "definition_th": ""},
            {"word": "หมา", "pinyin": "", "hsk_level": "nan", "definition": "", "definition_th": ""},
            {"word": "bad_level", "pinyin": "", "hsk_level": "99", "definition": "", "definition_th": ""},
        ],
    )
    words = load_wordlist_csv(csv_path, db_session)
    # both the NaN-level row and the out-of-range (1-9) row are skipped
    assert words == {"你好"}
    count = db_session.execute(text("SELECT COUNT(*) FROM hsk_wordlist")).scalar_one()
    assert count == 1


def test_load_wordlist_csv_upsert_updates_existing_word(db_session, tmp_path):
    first = _write_csv(tmp_path / "a", [{"word": "你好", "pinyin": "old", "hsk_level": "1", "definition": "", "definition_th": ""}])
    load_wordlist_csv(first, db_session)

    second = _write_csv(tmp_path / "b", [{"word": "你好", "pinyin": "new", "hsk_level": "2", "definition": "updated", "definition_th": ""}])
    load_wordlist_csv(second, db_session)

    count = db_session.execute(text("SELECT COUNT(*) FROM hsk_wordlist")).scalar_one()
    assert count == 1  # no duplicate row
    row = db_session.execute(text("SELECT pinyin, hsk_level, definition FROM hsk_wordlist WHERE word = '你好'")).mappings().one()
    assert row["pinyin"] == "new"
    assert row["hsk_level"] == 2
    assert row["definition"] == "updated"


def test_upsert_exam_source_insert_then_update(db_session):
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="old.pdf")
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="new.pdf")

    count = db_session.execute(text("SELECT COUNT(*) FROM exam_sources")).scalar_one()
    assert count == 1
    filename = db_session.execute(text("SELECT filename FROM exam_sources WHERE exam_id = '2020-01'")).scalar_one()
    assert filename == "new.pdf"


def test_upsert_exam_source_reading_and_listening_are_distinct_rows(db_session):
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="r.pdf")
    upsert_exam_source(db_session, exam_id="2020-01", source_type="listening", year=2020, hsk_level=3, filename="l.mp3")

    count = db_session.execute(text("SELECT COUNT(*) FROM exam_sources")).scalar_one()
    assert count == 2


def test_refresh_aggregates_sums_across_exams_and_builds_all_row(db_session):
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="r1.pdf")
    upsert_exam_source(db_session, exam_id="2021-02", source_type="reading", year=2021, hsk_level=4, filename="r2.pdf")
    upsert_exam_source(db_session, exam_id="2020-01", source_type="listening", year=2020, hsk_level=3, filename="l1.mp3")

    load_frequencies(
        db_session, Counter({"你好": 5}), source_type="reading", exam_id="2020-01",
        official_words={"你好"}, hsk_wordlist={"你好": {"hsk_level": 1}},
    )
    load_frequencies(
        db_session, Counter({"你好": 2}), source_type="reading", exam_id="2021-02",
        official_words={"你好"}, hsk_wordlist={"你好": {"hsk_level": 1}},
    )
    load_frequencies(
        db_session, Counter({"你好": 3}), source_type="listening", exam_id="2020-01",
        official_words={"你好"}, hsk_wordlist={"你好": {"hsk_level": 1}},
    )
    refresh_aggregates(db_session)

    rows = {
        r["source_type"]: dict(r)
        for r in db_session.execute(
            text("SELECT * FROM frequency_aggregates WHERE word = '你好'")
        ).mappings().all()
    }
    assert rows["reading"]["total_frequency"] == 7
    assert rows["reading"]["exam_count"] == 2
    assert rows["listening"]["total_frequency"] == 3
    assert rows["all"]["total_frequency"] == 10
    # 'all' groups by word only (not source_type), so the same physical exam
    # (2020-01, reading+listening) counts once, not twice -- 2 distinct exams total
    assert rows["all"]["exam_count"] == 2
    assert all(r["in_official_wordlist"] for r in rows.values())


def test_refresh_aggregates_is_rerunnable(db_session):
    """refresh_aggregates rebuilds via ON CONFLICT DO UPDATE -- running it twice
    in a row must not double-count."""
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="r.pdf")
    load_frequencies(
        db_session, Counter({"你好": 4}), source_type="reading", exam_id="2020-01",
        official_words=set(), hsk_wordlist={},
    )
    refresh_aggregates(db_session)
    refresh_aggregates(db_session)

    total = db_session.execute(
        text("SELECT total_frequency FROM frequency_aggregates WHERE word = '你好' AND source_type = 'all'")
    ).scalar_one()
    assert total == 4


def test_load_frequencies_upsert_replaces_frequency_on_rerun(db_session):
    upsert_exam_source(db_session, exam_id="2020-01", source_type="reading", year=2020, hsk_level=3, filename="r.pdf")
    load_frequencies(db_session, Counter({"你好": 5}), source_type="reading", exam_id="2020-01", official_words=set(), hsk_wordlist={})
    load_frequencies(db_session, Counter({"你好": 9}), source_type="reading", exam_id="2020-01", official_words=set(), hsk_wordlist={})

    count = db_session.execute(text("SELECT COUNT(*) FROM word_frequencies WHERE word = '你好'")).scalar_one()
    freq = db_session.execute(text("SELECT frequency FROM word_frequencies WHERE word = '你好'")).scalar_one()
    assert count == 1
    assert freq == 9
