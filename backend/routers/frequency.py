from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.db import get_db
from typing import Literal

router = APIRouter()


@router.get("/exams")
def list_exams(db: Session = Depends(get_db)):
    """List exams (reading + listening for the same exam_id merged into one entry)."""
    rows = db.execute(
        text("""
            SELECT
                exam_id,
                MAX(hsk_level) AS hsk_level,
                MAX(year) AS year,
                ARRAY_AGG(DISTINCT source_type ORDER BY source_type) AS source_types
            FROM exam_sources
            GROUP BY exam_id
            ORDER BY hsk_level, exam_id
        """)
    ).mappings().all()
    return {"items": [dict(r) for r in rows], "count": len(rows)}


@router.get("/top")
def top_words(
    hsk_level: int | None = Query(None, ge=1, le=9, description="Word's official HSK level (1-6)"),
    exam_level: int | None = Query(None, ge=1, le=9, description="HSK level of the exam paper itself (e.g. 3 or 4)"),
    exam_id: list[str] | None = Query(None, description="Filter to one or more specific exams (repeat the param); reading+listening are combined"),
    source_type: Literal["reading", "listening", "all"] = "all",
    limit: int = Query(50, ge=1, le=10000, description="Max rows to return; use a high value to fetch the full list"),
    db: Session = Depends(get_db),
):
    """Top N most frequent words, optionally filtered by word HSK level, exam-paper HSK level, one or more specific exams, and source type."""
    if exam_id:
        return _top_words_live(db, exam_ids=exam_id, exam_level=None, hsk_level=hsk_level, source_type=None, limit=limit)

    if exam_level is not None:
        return _top_words_live(db, exam_ids=None, exam_level=exam_level, hsk_level=hsk_level, source_type=source_type, limit=limit)

    conditions = ["1=1"]
    params: dict = {"limit": limit}

    if hsk_level is not None:
        conditions.append("hsk_level = :hsk_level")
        params["hsk_level"] = hsk_level

    if source_type != "all":
        conditions.append("source_type = :source_type")
        params["source_type"] = source_type
    else:
        conditions.append("source_type = 'all'")

    where = " AND ".join(conditions)
    rows = db.execute(
        text(f"""
            SELECT word, hsk_level, source_type, total_frequency, exam_count, in_official_wordlist
            FROM frequency_aggregates
            WHERE {where}
            ORDER BY total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    total_count = db.execute(
        text(f"SELECT COUNT(*) FROM frequency_aggregates WHERE {where}"),
        {k: v for k, v in params.items() if k != "limit"},
    ).scalar_one()

    return {"items": [dict(r) for r in rows], "count": len(rows), "total_count": total_count}


def _top_words_live(
    db: Session,
    exam_ids: list[str] | None,
    exam_level: int | None,
    hsk_level: int | None,
    source_type: str | None,
    limit: int,
):
    """Aggregate word_frequencies on the fly for an exam-scoped or exam-level-scoped view
    (frequency_aggregates has no per-exam / exam-level dimension, so it can't serve these)."""
    conditions = []
    params: dict = {"limit": limit}

    if exam_ids:
        conditions.append("wf.exam_id = ANY(:exam_ids)")
        params["exam_ids"] = exam_ids
    else:
        conditions.append("es.hsk_level = :exam_level")
        params["exam_level"] = exam_level
        if source_type is not None and source_type != "all":
            conditions.append("wf.source_type = :source_type")
            params["source_type"] = source_type

    if hsk_level is not None:
        conditions.append("wf.hsk_level = :hsk_level")
        params["hsk_level"] = hsk_level

    where = " AND ".join(conditions)
    rows = db.execute(
        text(f"""
            SELECT
                wf.word,
                wf.hsk_level,
                CASE WHEN COUNT(DISTINCT wf.source_type) > 1 THEN 'all' ELSE MIN(wf.source_type) END AS source_type,
                SUM(wf.frequency) AS total_frequency,
                COUNT(DISTINCT wf.exam_id) AS exam_count,
                BOOL_OR(wf.in_official_wordlist) AS in_official_wordlist
            FROM word_frequencies wf
            JOIN exam_sources es ON wf.exam_id = es.exam_id AND wf.source_type = es.source_type
            WHERE {where}
            GROUP BY wf.word, wf.hsk_level
            ORDER BY total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    total_count = db.execute(
        text(f"""
            SELECT COUNT(DISTINCT wf.word)
            FROM word_frequencies wf
            JOIN exam_sources es ON wf.exam_id = es.exam_id AND wf.source_type = es.source_type
            WHERE {where}
        """),
        {k: v for k, v in params.items() if k != "limit"},
    ).scalar_one()

    return {"items": [dict(r) for r in rows], "count": len(rows), "total_count": total_count}
