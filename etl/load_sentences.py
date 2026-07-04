"""Extract example sentences from raw exam texts and load them into exam_sentences.

Reading PDFs are noisy (answer options, question numbers, page markers), and
listening transcripts repeat every sentence twice (played twice in the exam),
so candidates are cleaned and deduplicated per (exam_id, source_type) before
insert.

Usage:
    python -m etl.load_sentences
"""
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.load_to_db import get_engine
from etl.logging_config import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_CJK_RE = re.compile(r"[一-鿿]")

# Sentence-final punctuation (full/half width); newlines also break sentences
# because reading PDFs put each item on its own line.
_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])|[\n\r]+")

# Leading exam scaffolding: question numbers ("11．", "２３."), CJK numerals
# with a following separator ("一,"), option letters ("A "), stars/brackets,
# and "例如：" — stripped repeatedly since they stack ("12．★ 他来北京6年了").
_LEAD_NOISE_RE = re.compile(
    r"^(?:\s+|例如|[0-9０-９]{1,3}\s*[.．、，,:：]|[一二三四五六七八九十]{1,3}\s*[.．、，,:：]"
    r"|[0-9０-９]{1,3}(?=[一-鿿])|[A-EＡ-Ｅ](?=[\s,，．.]|[一-鿿])"
    r"|[★☆•·▲←↑→↓□（）()\[\]【】“”\"'－—\-—.．、，,:：？?！!。；;]+)"
)

# Multiple-choice options that got merged onto one line ("老朋友 B 不认识的字 C ...")
# show up as isolated A-E letters mid-sentence; fill-in-the-blank items contain
# an empty-bracket blank "（ ）". Neither reads as a real example sentence.
_MID_NOISE_RE = re.compile(r"(?:^|[\s，,。.])[A-EＡ-Ｅ](?:[\s，,。.]|$)|[（(]\s*[）)]")


def _clean_candidate(raw: str) -> str | None:
    s = raw.strip()
    prev = None
    while prev != s:
        prev = s
        s = _LEAD_NOISE_RE.sub("", s).strip()

    cjk = len(_CJK_RE.findall(s))
    if cjk < 6 or len(s) > 80:
        return None
    if _MID_NOISE_RE.search(s):
        return None
    # Mostly-CJK check: drops OCR junk and English boilerplate lines.
    if cjk / len(s) < 0.6:
        return None
    return s


def extract_sentences(raw_text: str) -> list[str]:
    """Split one exam file's raw text into cleaned, deduplicated sentences."""
    seen: set[str] = set()
    result: list[str] = []
    for part in _SPLIT_RE.split(raw_text):
        if not part:
            continue
        cleaned = _clean_candidate(part)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


# A sentence appearing in this many different exams (or more) is exam
# boilerplate — instructions and the printed 例如 sample items are identical
# across papers. Genuine content is only ever reused between a couple of
# papers (HSK recycles some questions), so 2 exams is still plausible.
BOILERPLATE_EXAM_THRESHOLD = 3


def run():
    df = pd.read_parquet(DATA_DIR / "raw" / "raw_extractions.parquet")
    df = df.drop_duplicates(subset=["exam_id", "source_type"])

    per_file = [(row.exam_id, row.source_type, extract_sentences(row.text)) for row in df.itertuples()]

    exams_per_sentence: dict[str, set[str]] = {}
    for exam_id, _, sentences in per_file:
        for s in sentences:
            exams_per_sentence.setdefault(s, set()).add(exam_id)
    boilerplate = {s for s, exams in exams_per_sentence.items() if len(exams) >= BOILERPLATE_EXAM_THRESHOLD}
    logger.info("Dropping %d boilerplate sentences shared across >=%d exams", len(boilerplate), BOILERPLATE_EXAM_THRESHOLD)

    engine = get_engine()
    total = 0
    with Session(engine) as session:
        session.execute(text("DELETE FROM exam_sentences"))
        for exam_id, source_type, sentences in per_file:
            sentences = [s for s in sentences if s not in boilerplate]
            if sentences:
                session.execute(
                    text("""
                        INSERT INTO exam_sentences (exam_id, source_type, sentence)
                        VALUES (:exam_id, :source_type, :sentence)
                        ON CONFLICT (exam_id, source_type, sentence) DO NOTHING
                    """),
                    [
                        {"exam_id": exam_id, "source_type": source_type, "sentence": s}
                        for s in sentences
                    ],
                )
            total += len(sentences)
            logger.info("%s/%s: %d sentences", exam_id, source_type, len(sentences))
        session.commit()
    logger.info("Loaded %d sentences across %d files", total, len(df))


if __name__ == "__main__":
    run()
