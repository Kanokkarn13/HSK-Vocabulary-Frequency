"""Stage and atomically publish one complete ETL batch into PostgreSQL."""

from __future__ import annotations

from collections import defaultdict
import csv
from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.extract_wordlist import normalize_records, validate_wordlist
from etl.load_sentences import BOILERPLATE_EXAM_THRESHOLD, extract_sentences
from etl.load_to_db import get_engine
from etl.logging_config import get_logger


LOGGER = get_logger(__name__)
INSERT_CHUNK_SIZE = 5_000


def _sql_value(value: Any) -> Any:
    """Convert pandas NA/NaN values to SQL NULL instead of driver errors."""

    return None if value is None or pd.isna(value) else value

STAGE_DDL = """
CREATE TABLE IF NOT EXISTS etl_hsk_wordlist_stage (
    batch_id TEXT NOT NULL, word VARCHAR(50) NOT NULL, pinyin VARCHAR(100),
    hsk_level SMALLINT NOT NULL, definition TEXT, definition_th TEXT,
    PRIMARY KEY (batch_id, word)
);
CREATE TABLE IF NOT EXISTS etl_exam_sources_stage (
    batch_id TEXT NOT NULL, exam_id VARCHAR(100) NOT NULL, year SMALLINT,
    source_type VARCHAR(20) NOT NULL, hsk_level SMALLINT, filename VARCHAR(255),
    PRIMARY KEY (batch_id, exam_id, source_type)
);
CREATE TABLE IF NOT EXISTS etl_word_frequencies_stage (
    batch_id TEXT NOT NULL, word VARCHAR(50) NOT NULL, hsk_level SMALLINT,
    source_type VARCHAR(20) NOT NULL, exam_id VARCHAR(100) NOT NULL,
    frequency INTEGER NOT NULL, in_official_wordlist BOOLEAN NOT NULL,
    PRIMARY KEY (batch_id, word, source_type, exam_id)
);
CREATE TABLE IF NOT EXISTS etl_exam_sentences_stage (
    batch_id TEXT NOT NULL, exam_id VARCHAR(100) NOT NULL, source_type VARCHAR(20) NOT NULL,
    sentence TEXT NOT NULL, PRIMARY KEY (batch_id, exam_id, source_type, sentence)
);
CREATE TABLE IF NOT EXISTS etl_publish_state (
    state_key TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    production_counts JSONB NOT NULL
);
"""


def ensure_stage_tables(session: Session) -> None:
    for statement in STAGE_DDL.split(";"):
        if statement.strip():
            session.execute(text(statement))


def _clear_batch(session: Session, batch_id: str) -> None:
    for table in (
        "etl_exam_sentences_stage",
        "etl_word_frequencies_stage",
        "etl_exam_sources_stage",
        "etl_hsk_wordlist_stage",
    ):
        # The table name comes from a fixed tuple; batch_id remains bound.
        session.execute(text(f"DELETE FROM {table} WHERE batch_id = :batch_id"), {"batch_id": batch_id})  # nosec B608


def _execute_many(
    session: Session,
    statement: Any,
    rows: list[dict[str, Any]],
    *,
    copy_table: str | None = None,
    copy_columns: tuple[str, ...] = (),
) -> None:
    """Bulk-load rows in the current transaction, using PostgreSQL COPY when available."""

    if rows and copy_table:
        raw_connection = session.connection().connection
        cursor = raw_connection.cursor()
        if hasattr(cursor, "copy_expert"):
            stream = StringIO()
            writer = csv.writer(stream, lineterminator="\n")
            for row in rows:
                writer.writerow([r"\N" if row.get(column) is None else row[column] for column in copy_columns])
            stream.seek(0)
            cursor.copy_expert(
                f"COPY {copy_table} ({', '.join(copy_columns)}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                stream,
            )
            cursor.close()
            return
        cursor.close()

    for offset in range(0, len(rows), INSERT_CHUNK_SIZE):
        session.execute(statement, rows[offset : offset + INSERT_CHUNK_SIZE])


def _sentences_from_raw(raw: pd.DataFrame) -> list[dict[str, Any]]:
    per_exam: list[tuple[str, str, list[str]]] = []
    sentence_exams: dict[str, set[str]] = defaultdict(set)
    for row in raw.itertuples(index=False):
        sentences = extract_sentences(str(row.text or ""))
        per_exam.append((row.exam_id, row.source_type, sentences))
        for sentence in sentences:
            sentence_exams[sentence].add(row.exam_id)
    boilerplate = {
        sentence
        for sentence, exams in sentence_exams.items()
        if len(exams) >= BOILERPLATE_EXAM_THRESHOLD
    }
    return [
        {"exam_id": exam_id, "source_type": source_type, "sentence": sentence}
        for exam_id, source_type, sentences in per_exam
        for sentence in sentences
        if sentence not in boilerplate
    ]


def stage_batch(
    *,
    batch_id: str,
    wordlist_path: str | Path,
    raw_path: str | Path,
    counts_path: str | Path,
) -> dict[str, Any]:
    """Load all derived data into isolated staging tables in one transaction."""

    wordlist = normalize_records(pd.read_csv(wordlist_path, encoding="utf-8-sig").to_dict(orient="records"))
    quality = validate_wordlist(wordlist)
    raw = pd.read_parquet(raw_path).drop_duplicates(["exam_id", "source_type"])
    counts = pd.read_parquet(counts_path)
    required_counts = {"exam_id", "hsk_level", "source_type", "word", "count"}
    missing = required_counts - set(counts.columns)
    if missing:
        raise ValueError(f"Frequency artifact is missing columns: {sorted(missing)}")
    if raw.empty or counts.empty:
        raise ValueError("Cannot stage an empty raw snapshot or frequency artifact")

    counts = (
        counts.groupby(["exam_id", "hsk_level", "source_type", "word"], as_index=False)["count"].sum()
    )
    words = set(wordlist["word"].astype(str))
    hsk_levels = dict(zip(wordlist["word"].astype(str), wordlist["level"].astype(int)))
    source_columns = [column for column in ("exam_id", "source_type", "hsk_level", "filename", "year") if column in raw]
    sources = raw[source_columns].drop_duplicates()
    sentences = _sentences_from_raw(raw)

    engine = get_engine()
    with Session(engine) as session:
        ensure_stage_tables(session)
        _clear_batch(session, batch_id)
        _execute_many(
            session,
            text("""
                INSERT INTO etl_hsk_wordlist_stage
                    (batch_id, word, pinyin, hsk_level, definition, definition_th)
                VALUES (:batch_id, :word, :pinyin, :hsk_level, :definition, :definition_th)
            """),
            [
                {
                    "batch_id": batch_id,
                    "word": str(row.word),
                    "pinyin": _sql_value(row.pinyin),
                    "hsk_level": int(row.level),
                    "definition": _sql_value(row.definition),
                    "definition_th": _sql_value(row.definition_th),
                }
                for row in wordlist.itertuples(index=False)
            ],
            copy_table="etl_hsk_wordlist_stage",
            copy_columns=("batch_id", "word", "pinyin", "hsk_level", "definition", "definition_th"),
        )
        _execute_many(
            session,
            text("""
                INSERT INTO etl_exam_sources_stage
                    (batch_id, exam_id, year, source_type, hsk_level, filename)
                VALUES (:batch_id, :exam_id, :year, :source_type, :hsk_level, :filename)
            """),
            [
                {
                    "batch_id": batch_id,
                    "exam_id": row.exam_id,
                    "year": _sql_value(getattr(row, "year", None)),
                    "source_type": row.source_type,
                    "hsk_level": int(row.hsk_level) if pd.notna(row.hsk_level) else None,
                    "filename": _sql_value(getattr(row, "filename", None)),
                }
                for row in sources.itertuples(index=False)
            ],
            copy_table="etl_exam_sources_stage",
            copy_columns=("batch_id", "exam_id", "year", "source_type", "hsk_level", "filename"),
        )
        _execute_many(
            session,
            text("""
                INSERT INTO etl_word_frequencies_stage
                    (batch_id, word, hsk_level, source_type, exam_id, frequency, in_official_wordlist)
                VALUES (:batch_id, :word, :hsk_level, :source_type, :exam_id, :frequency, :in_official_wordlist)
            """),
            [
                {
                    "batch_id": batch_id,
                    "word": str(row.word),
                    "hsk_level": hsk_levels.get(str(row.word)),
                    "source_type": row.source_type,
                    "exam_id": row.exam_id,
                    "frequency": int(row.count),
                    "in_official_wordlist": str(row.word) in words,
                }
                for row in counts.itertuples(index=False)
            ],
            copy_table="etl_word_frequencies_stage",
            copy_columns=("batch_id", "word", "hsk_level", "source_type", "exam_id", "frequency", "in_official_wordlist"),
        )
        _execute_many(
            session,
            text("""
                INSERT INTO etl_exam_sentences_stage (batch_id, exam_id, source_type, sentence)
                VALUES (:batch_id, :exam_id, :source_type, :sentence)
            """),
            [{"batch_id": batch_id, **row} for row in sentences],
            copy_table="etl_exam_sentences_stage",
            copy_columns=("batch_id", "exam_id", "source_type", "sentence"),
        )
        session.commit()
        result = validate_stage(session, batch_id)
    engine.dispose()
    result["wordlist_quality"] = quality
    return result


def validate_stage(session: Session, batch_id: str) -> dict[str, Any]:
    counts = {}
    for table in (
        "etl_hsk_wordlist_stage",
        "etl_exam_sources_stage",
        "etl_word_frequencies_stage",
        "etl_exam_sentences_stage",
    ):
        counts[table] = int(
            # The table name comes from a fixed tuple; batch_id remains bound.
            session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE batch_id = :batch_id"), {"batch_id": batch_id}).scalar_one()  # nosec B608
        )
        if counts[table] == 0:
            raise ValueError(f"Staging quality check failed: {table} is empty")
    return {"batch_id": batch_id, "staging_counts": counts}


def publish_batch(batch_id: str) -> dict[str, Any]:
    """Atomically replace production tables from one validated batch."""

    engine = get_engine()
    with Session(engine) as session:
        with session.begin():
            ensure_stage_tables(session)
            validate_stage(session, batch_id)
            # Delete in FK-safe order. The transaction keeps the previous
            # committed dataset visible until all inserts succeed.
            for table in ("exam_sentences", "frequency_aggregates", "word_frequencies", "exam_sources", "hsk_wordlist"):
                # The table name comes from a fixed tuple.
                session.execute(text(f"DELETE FROM {table}"))  # nosec B608
            session.execute(text("""
                INSERT INTO hsk_wordlist (word, pinyin, hsk_level, definition, definition_th)
                SELECT word, pinyin, hsk_level, definition, definition_th
                FROM etl_hsk_wordlist_stage WHERE batch_id = :batch_id
            """), {"batch_id": batch_id})
            session.execute(text("""
                INSERT INTO exam_sources (exam_id, year, source_type, hsk_level, filename)
                SELECT exam_id, year, source_type, hsk_level, filename
                FROM etl_exam_sources_stage WHERE batch_id = :batch_id
            """), {"batch_id": batch_id})
            session.execute(text("""
                INSERT INTO word_frequencies (word, hsk_level, source_type, exam_id, frequency, in_official_wordlist)
                SELECT word, hsk_level, source_type, exam_id, frequency, in_official_wordlist
                FROM etl_word_frequencies_stage WHERE batch_id = :batch_id
            """), {"batch_id": batch_id})
            session.execute(text("""
                INSERT INTO frequency_aggregates
                    (word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist)
                SELECT word, MAX(hsk_level), source_type, SUM(frequency), COUNT(DISTINCT exam_id), BOOL_OR(in_official_wordlist)
                FROM word_frequencies GROUP BY word, source_type
                ON CONFLICT (word, source_type) DO UPDATE SET
                    hsk_level = EXCLUDED.hsk_level,
                    total_frequency = EXCLUDED.total_frequency,
                    exam_count = EXCLUDED.exam_count,
                    in_official_wordlist = EXCLUDED.in_official_wordlist,
                    updated_at = NOW()
            """))
            session.execute(text("""
                INSERT INTO frequency_aggregates
                    (word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist)
                SELECT word, MAX(hsk_level), 'all', SUM(frequency), COUNT(DISTINCT exam_id), BOOL_OR(in_official_wordlist)
                FROM word_frequencies GROUP BY word
                ON CONFLICT (word, source_type) DO UPDATE SET
                    hsk_level = EXCLUDED.hsk_level,
                    total_frequency = EXCLUDED.total_frequency,
                    exam_count = EXCLUDED.exam_count,
                    in_official_wordlist = EXCLUDED.in_official_wordlist,
                    updated_at = NOW()
            """))
            session.execute(text("""
                INSERT INTO exam_sentences (exam_id, source_type, sentence)
                SELECT exam_id, source_type, sentence
                FROM etl_exam_sentences_stage WHERE batch_id = :batch_id
            """), {"batch_id": batch_id})
            production_counts = {
                # The table name comes from a fixed tuple.
                table: int(session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())  # nosec B608
                for table in (
                    "hsk_wordlist",
                    "exam_sources",
                    "word_frequencies",
                    "frequency_aggregates",
                    "exam_sentences",
                )
            }
            session.execute(text("""
                INSERT INTO etl_publish_state (state_key, batch_id, published_at, production_counts)
                VALUES ('production', :batch_id, NOW(), CAST(:production_counts AS JSONB))
                ON CONFLICT (state_key) DO UPDATE SET
                    batch_id = EXCLUDED.batch_id,
                    published_at = EXCLUDED.published_at,
                    production_counts = EXCLUDED.production_counts
            """), {"batch_id": batch_id, "production_counts": json.dumps(production_counts)})
            result = {
                "batch_id": batch_id,
                "production_counts": production_counts,
            }
    engine.dispose()
    return result


__all__ = ["ensure_stage_tables", "publish_batch", "stage_batch", "validate_stage"]
