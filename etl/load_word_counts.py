"""Load the notebook pipeline's output (word_counts.parquet, raw_extractions.parquet,
hsk_wordlist.csv) into Postgres. This is the bridge between notebooks 01/02 and the
FastAPI backend — run after re-running those notebooks to refresh the DB.

Usage:
    python -m etl.load_word_counts
"""
from collections import Counter
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.load_to_db import (
    get_engine,
    load_frequencies,
    load_wordlist_csv,
    upsert_exam_source,
    refresh_aggregates,
)
from etl.logging_config import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def run():
    engine = get_engine()
    with Session(engine) as session:
        official_words = load_wordlist_csv(DATA_DIR / "processed" / "hsk_wordlist.csv", session)

        exams = pd.read_parquet(DATA_DIR / "raw" / "raw_extractions.parquet")
        exams = exams.drop_duplicates(subset=["exam_id", "source_type"])
        for row in exams.itertuples():
            upsert_exam_source(
                session,
                exam_id=row.exam_id,
                source_type=row.source_type,
                year=None,
                hsk_level=int(row.hsk_level) if pd.notna(row.hsk_level) else None,
                filename=row.filename,
            )
        logger.info("Loaded %d exam sources", len(exams))

        counts = pd.read_parquet(DATA_DIR / "processed" / "word_counts.parquet")
        hsk_wordlist = {
            r["word"]: dict(r)
            for r in session.execute(text("SELECT word, pinyin, hsk_level FROM hsk_wordlist")).mappings()
        }

        exam_groups = counts.groupby(["exam_id", "source_type"])
        for (exam_id, source_type), group in exam_groups:
            counter = Counter(dict(zip(group["word"], group["count"])))
            load_frequencies(session, counter, source_type, exam_id, official_words, hsk_wordlist)

        refresh_aggregates(session)
        logger.info("Loaded %d word-frequency rows across %d exams", len(counts), exam_groups.ngroups)


if __name__ == "__main__":
    run()
