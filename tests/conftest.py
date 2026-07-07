"""Shared fixtures for DB-backed tests.

Needs a reachable Postgres matching backend/db.py's env-var defaults
(DB_USER=hsk_user, DB_PASSWORD=changeme, DB_NAME=hsk_frequency,
DB_HOST=localhost, DB_PORT=5432) -- the same defaults docker-compose's `db`
service uses. Run `docker compose up -d db` before running tests locally;
CI spins up an equivalent Postgres service container (see ci-cd.yml).

Tests that don't touch the DB (test_segment.py, the UA-blocking tests in
test_api.py) never request the `db_session` fixture, so they don't need
Postgres running at all.
"""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import engine as api_engine

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

# Order doesn't matter for TRUNCATE ... CASCADE; listed for clarity of what a
# "clean slate" resets.
TABLES = (
    "exam_sentences",
    "word_frequencies",
    "frequency_aggregates",
    "exam_sources",
    "hsk_wordlist",
)


@pytest.fixture(scope="session")
def _schema_applied():
    """Apply db/schema.sql once per test session. CREATE TABLE IF NOT EXISTS
    throughout makes this idempotent against an already-initialized DB."""
    with api_engine.connect() as conn:
        conn.exec_driver_sql(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


@pytest.fixture
def db_session(_schema_applied):
    """Truncates every table for a clean slate, then hands back a session for
    the test to seed fixture rows into (commit it yourself, or use the
    `seeded_db` fixture below for the standard dataset)."""
    with Session(api_engine) as session:
        session.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        session.commit()
        yield session
        session.close()


# A small, realistic fixture dataset shared by the router tests: two exams
# (one HSK3 reading+listening pair, one HSK4 reading-only), four words with
# different official-wordlist / cross-exam-frequency shapes, chosen so no two
# "all"-aggregate totals tie (keeps ORDER BY total_frequency DESC deterministic).
def seed_sample_data(session: Session):
    session.execute(
        text("""
            INSERT INTO hsk_wordlist (word, pinyin, hsk_level, definition, definition_th)
            VALUES
                ('你好', 'nǐ hǎo', 1, 'hello', 'สวัสดี'),
                ('谢谢', 'xiè xie', 1, 'thank you', 'ขอบคุณ'),
                ('因为', 'yīn wèi', 3, 'because', 'เพราะว่า')
        """)
    )
    session.execute(
        text("""
            INSERT INTO exam_sources (exam_id, source_type, year, hsk_level, filename)
            VALUES
                ('2020-01', 'reading', 2020, 3, 'reading_2020_01.pdf'),
                ('2020-01', 'listening', 2020, 3, 'listening_2020_01.mp3'),
                ('2021-02', 'reading', 2021, 4, 'reading_2021_02.pdf')
        """)
    )
    session.execute(
        text("""
            INSERT INTO word_frequencies (word, hsk_level, source_type, exam_id, frequency, in_official_wordlist)
            VALUES
                ('你好', 1, 'reading', '2020-01', 5, TRUE),
                ('你好', 1, 'listening', '2020-01', 3, TRUE),
                ('你好', 1, 'reading', '2021-02', 2, TRUE),
                ('谢谢', 1, 'reading', '2020-01', 1, TRUE),
                ('因为', 3, 'reading', '2021-02', 10, TRUE),
                ('喵星人', NULL, 'reading', '2021-02', 1, FALSE)
        """)
    )
    session.execute(
        text("""
            INSERT INTO frequency_aggregates (word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist)
            VALUES
                ('你好', 1, 'reading', 7, 2, TRUE),
                ('你好', 1, 'listening', 3, 1, TRUE),
                ('你好', 1, 'all', 10, 2, TRUE),
                ('谢谢', 1, 'reading', 1, 1, TRUE),
                ('谢谢', 1, 'all', 1, 1, TRUE),
                ('因为', 3, 'reading', 8, 1, TRUE),
                ('因为', 3, 'all', 8, 1, TRUE),
                ('喵星人', NULL, 'reading', 1, 1, FALSE),
                ('喵星人', NULL, 'all', 1, 1, FALSE)
        """)
    )
    session.execute(
        text("""
            INSERT INTO exam_sentences (exam_id, source_type, sentence)
            VALUES
                ('2020-01', 'reading', '你好，我叫小明。'),
                ('2020-01', 'listening', '你好你好，请问现在几点了？'),
                ('2021-02', 'reading', '因为下雨，所以我们没有去公园。')
        """)
    )
    session.commit()


@pytest.fixture
def seeded_db(db_session):
    """db_session with the standard sample dataset already inserted/committed."""
    seed_sample_data(db_session)
    return db_session


# The API blocks requests with no/known-scraper User-Agent (backend/main.py) --
# every test client request needs a header that doesn't match that blocklist.
BROWSER_HEADERS = {"User-Agent": "pytest-suite"}
