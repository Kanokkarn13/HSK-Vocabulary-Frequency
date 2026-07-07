"""Compare the live database's schema against db/schema.sql.

`CREATE TABLE IF NOT EXISTS` (what schema.sql uses throughout) is a no-op
against a table that already exists -- it will never add a column that was
added to schema.sql after the table was first created. That silent gap is
exactly what caused the 2026-07-07 production incident: hsk_wordlist.definition/
definition_th and the exam_sentences table were added to schema.sql, applied
locally, but never migrated onto the already-existing Neon database, so
GET /api/search/word-detail 500'd on every request in production while every
test passed (tests always re-apply the current schema.sql fresh).

This script is the guardrail: run it against Neon (or any deployed DB) before
and after a schema change to catch drift before it ships.

Usage:
    DB_HOST=<neon-host> DB_USER=... DB_PASSWORD=... DB_NAME=... DB_SSLMODE=require \\
        python -m scripts.check_schema_drift

Exits non-zero and lists every missing table/column if the connected database
is behind schema.sql. Exits 0 (silent) if it matches.
"""
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.db import DATABASE_URL

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", re.DOTALL
)
# A column line starts with an identifier followed by a type -- constraint-only
# lines (UNIQUE (...), FOREIGN KEY (...), CHECK (...)) look similar but start
# with a reserved keyword instead of a column name, so exclude those.
_TABLE_CONSTRAINT_KEYWORDS = {"unique", "foreign", "primary", "check", "constraint"}
_COLUMN_RE = re.compile(r"^\s*(\w+)\s+[A-Z]")


def expected_schema() -> dict[str, set[str]]:
    """Parse {table_name: {column_name, ...}} straight out of schema.sql."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    schema: dict[str, set[str]] = {}
    for table_name, body in _TABLE_RE.findall(sql):
        columns = set()
        for line in body.split(","):
            m = _COLUMN_RE.match(line)
            if m and m.group(1).lower() not in _TABLE_CONSTRAINT_KEYWORDS:
                columns.add(m.group(1).lower())
        schema[table_name.lower()] = columns
    return schema


def actual_schema(engine) -> dict[str, set[str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """)
        ).all()
    schema: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        schema.setdefault(table_name.lower(), set()).add(column_name.lower())
    return schema


def diff(expected: dict[str, set[str]], actual: dict[str, set[str]]) -> list[str]:
    problems = []
    for table, columns in expected.items():
        if table not in actual:
            problems.append(f"missing table: {table}")
            continue
        for column in sorted(columns - actual[table]):
            problems.append(f"missing column: {table}.{column}")
    return problems


def main() -> int:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    problems = diff(expected_schema(), actual_schema(engine))
    if not problems:
        print("Schema OK: connected database matches db/schema.sql.")
        return 0

    print("Schema drift detected -- connected database is behind db/schema.sql:")
    for p in problems:
        print(f"  - {p}")
    print("\nApply db/schema.sql (and any needed ALTER TABLE ... ADD COLUMN IF NOT "
          "EXISTS for columns added to an existing table) against this database, "
          "then re-run the relevant etl/load_*.py loader(s). See "
          "wiki/deploy-vercel.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
