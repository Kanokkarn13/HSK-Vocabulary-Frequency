from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.db import get_db

router = APIRouter()


@router.get("/wordlist-vs-actual")
def compare_wordlist(
    hsk_level: int | None = Query(None, ge=1, le=9, description="Word's official HSK level (1-6)"),
    exam_level: int | None = Query(None, ge=1, le=9, description="HSK level of the exam paper itself (e.g. 3 or 4)"),
    exam_id: str | None = Query(None, description="Filter to one specific exam; reading+listening are combined"),
    source_type: str = "all",
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Words that appear frequently in exams but are NOT in the official HSK wordlist,
    and words that ARE in the official wordlist sorted by how often they actually appear.
    """
    if exam_id is not None or exam_level is not None:
        return _compare_live(db, exam_id=exam_id, exam_level=exam_level, hsk_level=hsk_level, source_type=source_type, limit=limit)

    params: dict = {"limit": limit}
    level_filter = "AND fa.hsk_level = :hsk_level" if hsk_level else ""
    if hsk_level:
        params["hsk_level"] = hsk_level

    source_filter = "AND fa.source_type = :source_type" if source_type != "all" else "AND fa.source_type = 'all'"
    if source_type != "all":
        params["source_type"] = source_type

    not_in_wordlist = db.execute(
        text(f"""
            SELECT word, hsk_level, total_frequency, exam_count
            FROM frequency_aggregates fa
            WHERE in_official_wordlist = FALSE {level_filter} {source_filter}
            ORDER BY total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    in_wordlist = db.execute(
        text(f"""
            SELECT fa.word, fa.hsk_level, fa.total_frequency, fa.exam_count, hw.pinyin
            FROM frequency_aggregates fa
            JOIN hsk_wordlist hw ON fa.word = hw.word
            WHERE fa.in_official_wordlist = TRUE {level_filter} {source_filter}
            ORDER BY fa.total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    return {
        "not_in_official_wordlist": [dict(r) for r in not_in_wordlist],
        "in_official_wordlist": [dict(r) for r in in_wordlist],
    }


def _compare_live(
    db: Session,
    exam_id: str | None,
    exam_level: int | None,
    hsk_level: int | None,
    source_type: str,
    limit: int,
):
    """Same as compare_wordlist but scoped to one exam or one exam-paper HSK level,
    aggregated live from word_frequencies since frequency_aggregates has no exam dimension."""
    conditions = []
    params: dict = {"limit": limit}

    if exam_id is not None:
        conditions.append("wf.exam_id = :exam_id")
        params["exam_id"] = exam_id
    else:
        conditions.append("es.hsk_level = :exam_level")
        params["exam_level"] = exam_level
        if source_type != "all":
            conditions.append("wf.source_type = :source_type")
            params["source_type"] = source_type

    if hsk_level is not None:
        conditions.append("wf.hsk_level = :hsk_level")
        params["hsk_level"] = hsk_level

    where = " AND ".join(conditions)

    not_in_wordlist = db.execute(
        text(f"""
            SELECT wf.word, wf.hsk_level, SUM(wf.frequency) AS total_frequency,
                   COUNT(DISTINCT wf.exam_id) AS exam_count
            FROM word_frequencies wf
            JOIN exam_sources es ON wf.exam_id = es.exam_id AND wf.source_type = es.source_type
            WHERE wf.in_official_wordlist = FALSE AND {where}
            GROUP BY wf.word, wf.hsk_level
            ORDER BY total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    in_wordlist = db.execute(
        text(f"""
            SELECT wf.word, wf.hsk_level, SUM(wf.frequency) AS total_frequency,
                   COUNT(DISTINCT wf.exam_id) AS exam_count, MIN(hw.pinyin) AS pinyin
            FROM word_frequencies wf
            JOIN exam_sources es ON wf.exam_id = es.exam_id AND wf.source_type = es.source_type
            JOIN hsk_wordlist hw ON wf.word = hw.word
            WHERE wf.in_official_wordlist = TRUE AND {where}
            GROUP BY wf.word, wf.hsk_level
            ORDER BY total_frequency DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()

    return {
        "not_in_official_wordlist": [dict(r) for r in not_in_wordlist],
        "in_official_wordlist": [dict(r) for r in in_wordlist],
    }
