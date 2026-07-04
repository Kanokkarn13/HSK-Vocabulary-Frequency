from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.db import get_db

router = APIRouter()


@router.get("/word")
def search_word(
    q: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
):
    """Search for a specific word and return its frequency across all sources."""
    rows = db.execute(
        text("""
            SELECT
                wf.word, wf.hsk_level, wf.source_type, wf.exam_id,
                wf.frequency, wf.in_official_wordlist,
                es.year, es.filename
            FROM word_frequencies wf
            LEFT JOIN exam_sources es
                ON wf.exam_id = es.exam_id AND wf.source_type = es.source_type
            WHERE wf.word = :word
            ORDER BY wf.frequency DESC
        """),
        {"word": q},
    ).mappings().all()

    aggregates = db.execute(
        text("""
            SELECT word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist
            FROM frequency_aggregates
            WHERE word = :word
        """),
        {"word": q},
    ).mappings().all()

    return {
        "word": q,
        "aggregates": [dict(r) for r in aggregates],
        "occurrences": [dict(r) for r in rows],
    }
