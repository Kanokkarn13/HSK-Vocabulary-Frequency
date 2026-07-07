from backend.db import engine as api_engine
from scripts.check_schema_drift import actual_schema, diff, expected_schema, main


def test_expected_schema_parses_tables_and_columns_from_schema_sql():
    schema = expected_schema()

    assert "hsk_wordlist" in schema
    assert {"word", "pinyin", "hsk_level", "definition", "definition_th"} <= schema["hsk_wordlist"]
    assert "exam_sentences" in schema
    assert {"exam_id", "source_type", "sentence"} <= schema["exam_sentences"]


def test_expected_schema_excludes_constraint_only_lines():
    schema = expected_schema()

    # word_frequencies has a UNIQUE (...) and a FOREIGN KEY (...) line that
    # must not be mistaken for columns named "unique"/"foreign".
    assert "unique" not in schema["word_frequencies"]
    assert "foreign" not in schema["word_frequencies"]


def test_actual_schema_matches_expected_schema_after_migration(db_session):
    # db_session's _schema_applied fixture has already run db/schema.sql
    # against api_engine, so the live DB should have every expected column.
    expected = expected_schema()
    actual = actual_schema(api_engine)

    for table, columns in expected.items():
        assert table in actual
        assert columns <= actual[table]


def test_diff_reports_missing_table():
    expected = {"hsk_wordlist": {"word", "pinyin"}}
    actual: dict[str, set[str]] = {}

    problems = diff(expected, actual)

    assert problems == ["missing table: hsk_wordlist"]


def test_diff_reports_missing_column():
    expected = {"hsk_wordlist": {"word", "pinyin", "definition_th"}}
    actual = {"hsk_wordlist": {"word", "pinyin"}}

    problems = diff(expected, actual)

    assert problems == ["missing column: hsk_wordlist.definition_th"]


def test_diff_is_empty_when_actual_is_a_superset():
    expected = {"hsk_wordlist": {"word"}}
    actual = {"hsk_wordlist": {"word", "pinyin", "created_at"}}

    assert diff(expected, actual) == []


def test_main_returns_zero_when_no_drift(db_session, capsys):
    exit_code = main()

    assert exit_code == 0
    assert "Schema OK" in capsys.readouterr().out


def test_main_returns_nonzero_and_lists_problems_on_drift(db_session, monkeypatch, capsys):
    monkeypatch.setattr(
        "scripts.check_schema_drift.diff",
        lambda expected, actual: ["missing column: hsk_wordlist.definition_th"],
    )

    exit_code = main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "Schema drift detected" in out
    assert "missing column: hsk_wordlist.definition_th" in out
