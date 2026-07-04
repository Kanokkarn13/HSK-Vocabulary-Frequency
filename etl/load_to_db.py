"""Load frequency data into the PostgreSQL database."""
import csv
import os
from collections import Counter
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from etl.logging_config import get_logger

logger = get_logger(__name__)


def get_engine():
    url = (
        f"postgresql://{os.getenv('DB_USER', 'hsk_user')}:"
        f"{os.getenv('DB_PASSWORD', 'changeme')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'hsk_frequency')}"
    )
    if os.getenv("DB_SSLMODE"):
        url += f"?sslmode={os.getenv('DB_SSLMODE')}"
    poolclass = NullPool if os.getenv("VERCEL") else None
    return create_engine(url, pool_pre_ping=True, poolclass=poolclass)


def load_wordlist_csv(csv_path: str | Path, session: Session) -> set[str]:
    """Load HSK wordlist snapshot CSV into hsk_wordlist table. Returns set of words."""
    words = set()
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row["word"].strip()
            raw_level = row.get("hsk_level") or row.get("level")
            hsk_level = int(float(raw_level)) if raw_level not in (None, "", "nan") else 0
            if not 1 <= hsk_level <= 9:
                logger.warning("Skipping bad wordlist row (word=%r, level=%r) — source data issue", word, raw_level)
                continue
            session.execute(
                text("""
                    INSERT INTO hsk_wordlist (word, pinyin, hsk_level)
                    VALUES (:word, :pinyin, :hsk_level)
                    ON CONFLICT (word) DO UPDATE SET
                        pinyin = EXCLUDED.pinyin,
                        hsk_level = EXCLUDED.hsk_level
                """),
                {
                    "word": word,
                    "pinyin": row.get("pinyin", "").strip(),
                    "hsk_level": hsk_level,
                },
            )
            words.add(word)
    session.commit()
    logger.info("Loaded %d words into hsk_wordlist", len(words))
    return words


def upsert_exam_source(
    session: Session,
    exam_id: str,
    source_type: str,
    year: int | None,
    hsk_level: int | None,
    filename: str,
):
    session.execute(
        text("""
            INSERT INTO exam_sources (exam_id, source_type, year, hsk_level, filename)
            VALUES (:exam_id, :source_type, :year, :hsk_level, :filename)
            ON CONFLICT (exam_id, source_type) DO UPDATE SET
                year = EXCLUDED.year,
                hsk_level = EXCLUDED.hsk_level,
                filename = EXCLUDED.filename
        """),
        {
            "exam_id": exam_id,
            "source_type": source_type,
            "year": year,
            "hsk_level": hsk_level,
            "filename": filename,
        },
    )
    session.commit()


def load_frequencies(
    session: Session,
    counter: Counter,
    source_type: str,
    exam_id: str,
    official_words: set[str],
    hsk_wordlist: dict[str, dict],
):
    """Insert per-exam word frequencies. Call refresh_aggregates() once after
    loading all exams in a batch — it's a full-table rebuild, not incremental."""
    for word, freq in counter.items():
        in_wl = word in official_words
        hsk_level = hsk_wordlist.get(word, {}).get("hsk_level")
        session.execute(
            text("""
                INSERT INTO word_frequencies (word, hsk_level, source_type, exam_id, frequency, in_official_wordlist)
                VALUES (:word, :hsk_level, :source_type, :exam_id, :frequency, :in_wl)
                ON CONFLICT (word, source_type, exam_id)
                DO UPDATE SET frequency = EXCLUDED.frequency
            """),
            {
                "word": word,
                "hsk_level": hsk_level,
                "source_type": source_type,
                "exam_id": exam_id,
                "frequency": freq,
                "in_wl": in_wl,
            },
        )

    session.commit()
    logger.info("Loaded %d words for exam_id=%s", len(counter), exam_id)


def refresh_aggregates(session: Session):
    """Rebuild frequency_aggregates from word_frequencies."""
    session.execute(text("""
        INSERT INTO frequency_aggregates (word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist)
        SELECT
            word,
            hsk_level,
            source_type,
            SUM(frequency),
            COUNT(DISTINCT exam_id),
            BOOL_OR(in_official_wordlist)
        FROM word_frequencies
        GROUP BY word, hsk_level, source_type
        ON CONFLICT (word, source_type)
        DO UPDATE SET
            hsk_level = EXCLUDED.hsk_level,
            total_frequency = EXCLUDED.total_frequency,
            exam_count = EXCLUDED.exam_count,
            in_official_wordlist = EXCLUDED.in_official_wordlist,
            updated_at = NOW();

        -- also upsert 'all' aggregate
        INSERT INTO frequency_aggregates (word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist)
        SELECT
            word,
            hsk_level,
            'all',
            SUM(frequency),
            COUNT(DISTINCT exam_id),
            BOOL_OR(in_official_wordlist)
        FROM word_frequencies
        GROUP BY word, hsk_level
        ON CONFLICT (word, source_type)
        DO UPDATE SET
            hsk_level = EXCLUDED.hsk_level,
            total_frequency = EXCLUDED.total_frequency,
            exam_count = EXCLUDED.exam_count,
            in_official_wordlist = EXCLUDED.in_official_wordlist,
            updated_at = NOW();
    """))
    session.commit()
