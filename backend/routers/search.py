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


MAX_EXAMPLE_SENTENCES = 10


@router.get("/word-detail")
def word_detail(
    q: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
):
    """Pinyin, definitions, and up to 10 example sentences (with source files)
    for a single word. Examples are spread across files (one per file first)
    and prefer medium-length sentences, which read best as examples."""
    info = db.execute(
        text("""
            SELECT word, pinyin, hsk_level, definition, definition_th
            FROM hsk_wordlist
            WHERE word = :word
        """),
        {"word": q},
    ).mappings().first()

    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"

    totals = db.execute(
        text("""
            SELECT
                COUNT(DISTINCT sentence) AS sentence_total,
                COUNT(DISTINCT (exam_id, source_type)) AS file_total
            FROM exam_sentences
            WHERE sentence LIKE :pattern
        """),
        {"pattern": pattern},
    ).mappings().one()

    # Inner DISTINCT ON collapses the same sentence text reused across files
    # (HSK recycles some items) to a single source; outer DISTINCT ON then
    # picks one representative sentence per remaining file, closest to 20
    # characters (reads best as a standalone example).
    sentences = db.execute(
        text("""
            SELECT s.sentence, s.exam_id, s.source_type, es.filename, es.hsk_level AS exam_hsk_level
            FROM (
                SELECT DISTINCT ON (exam_id, source_type) sentence, exam_id, source_type
                FROM (
                    SELECT DISTINCT ON (sentence) sentence, exam_id, source_type
                    FROM exam_sentences
                    WHERE sentence LIKE :pattern
                    ORDER BY sentence, exam_id, source_type
                ) dedup
                ORDER BY exam_id, source_type, ABS(LENGTH(sentence) - 20)
            ) s
            JOIN exam_sources es
                ON s.exam_id = es.exam_id AND s.source_type = es.source_type
            ORDER BY ABS(LENGTH(s.sentence) - 20)
            LIMIT :limit
        """),
        {"pattern": pattern, "limit": MAX_EXAMPLE_SENTENCES},
    ).mappings().all()

    return {
        "word": q,
        "in_wordlist": info is not None,
        "pinyin": info["pinyin"] if info else None,
        "hsk_level": info["hsk_level"] if info else None,
        "definition": info["definition"] if info else None,
        "definition_th": info["definition_th"] if info else None,
        "sentence_total": totals["sentence_total"],
        "file_total": totals["file_total"],
        "sentences": [dict(r) for r in sentences],
    }
