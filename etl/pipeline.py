"""
Main ETL entry point.

Usage:
    python -m etl.pipeline --source-type reading --input-dir data/reading
    python -m etl.pipeline --source-type listening --input-dir data/listening --whisper-model medium
"""
import argparse
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.extract_pdf import extract_all_pdfs
from etl.transcribe_audio import transcribe_all
from etl.segment_and_count import count_per_source
from etl.load_to_db import (
    get_engine,
    load_wordlist_csv,
    upsert_exam_source,
    load_frequencies,
    refresh_aggregates,
)
from etl.logging_config import get_logger

logger = get_logger(__name__)


def parse_filename_metadata(filename: str) -> tuple[str | None, int | None]:
    """Best-effort parse year and HSK level from filename like 'HSK4_2019_listening.mp3'."""
    import re
    year_match = re.search(r"(20\d{2})", filename)
    level_match = re.search(r"[Hh][Ss][Kk](\d)", filename)
    year = int(year_match.group(1)) if year_match else None
    level = int(level_match.group(1)) if level_match else None
    return year, level


def run(source_type: str, input_dir: str, wordlist_csv: str, whisper_model: str | None):
    engine = get_engine()
    with Session(engine) as session:
        # Load wordlist
        wordlist_path = Path(wordlist_csv)
        official_words = load_wordlist_csv(wordlist_path, session)

        # Build hsk_wordlist lookup
        rows = session.execute(
            text("SELECT word, pinyin, hsk_level FROM hsk_wordlist")
        ).mappings().all()
        hsk_lookup = {r["word"]: dict(r) for r in rows}

        # Extract text
        if source_type == "reading":
            texts = extract_all_pdfs(input_dir)
        else:
            texts = transcribe_all(input_dir, whisper_model)

        per_source = count_per_source(texts)

        for filename, counter in per_source.items():
            year, hsk_level = parse_filename_metadata(filename)
            exam_id = f"{source_type}_{Path(filename).stem}"
            upsert_exam_source(session, exam_id, source_type, year, hsk_level, filename)
            load_frequencies(session, counter, source_type, exam_id, official_words, hsk_lookup)

        refresh_aggregates(session)

    logger.info("Pipeline run complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", choices=["reading", "listening"], required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--wordlist-csv", default="data/wordlist/hsk_wordlist.csv")
    parser.add_argument("--whisper-model", default=None)
    args = parser.parse_args()

    run(args.source_type, args.input_dir, args.wordlist_csv, args.whisper_model)
