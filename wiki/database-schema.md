# Database Schema

Database: PostgreSQL 16  
Schema defined in: [`db/schema.sql`](../db/schema.sql)

---

## Tables

### `hsk_wordlist`

The official HSK vocabulary reference. Loaded from a CSV snapshot — never queried live from the flashcard app.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `word` | VARCHAR(50) UNIQUE | Simplified Chinese |
| `pinyin` | VARCHAR(100) | Optional |
| `hsk_level` | SMALLINT | 1–9 (old HSK 1–6 maps to 1–6) |
| `definition` | TEXT | English gloss, from the wordlist snapshot CSV |
| `definition_th` | TEXT | Thai gloss, same source |
| `created_at` | TIMESTAMPTZ | |

`definition`/`definition_th` are loaded by `load_wordlist_csv()` in
`etl/load_to_db.py` from the `definition`/`definition_th` columns already
present in `data/processed/hsk_wordlist.csv` — added 2026-07-04 to power the
word-detail lookup (`GET /api/search/word-detail`, see
[API Endpoints](api-endpoints.md)), no new data source needed.

---

### `exam_sources`

One row **per (exam file, source type)** — each exam has a separate reading
(PDF) row and listening (audio) row, since they're different physical files
with different filenames sharing the same `exam_id`.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `exam_id` | VARCHAR(100) | e.g. `H31001`. **Not unique alone** — see below |
| `year` | SMALLINT | Parsed from filename, nullable |
| `source_type` | VARCHAR(20) | `reading` or `listening` |
| `hsk_level` | SMALLINT | The exam paper's own HSK level (3 or 4 in this corpus), nullable |
| `filename` | VARCHAR(255) | Original filename |
| `processed_at` | TIMESTAMPTZ | |

Unique constraint: `(exam_id, source_type)`.

> **Fixed bug:** this was originally `UNIQUE (exam_id)` alone with
> `ON CONFLICT (exam_id) DO NOTHING`. Since reading and listening for the
> same exam share an `exam_id`, only whichever source type loaded *first*
> ever got a row — the other's filename was silently dropped, and any query
> joining on `exam_id` alone (e.g. `/api/search/word`) could return the
> wrong file's name for the other source type. Fixed by making the
> constraint `(exam_id, source_type)` and updating the conflict target to
> `ON CONFLICT (exam_id, source_type) DO UPDATE ...`.

---

### `word_frequencies`

Raw frequency counts — one row per (word, source_type, exam_id).

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `word` | VARCHAR(50) | |
| `hsk_level` | SMALLINT | From wordlist join, nullable if not in wordlist |
| `source_type` | VARCHAR(20) | `reading` or `listening` |
| `exam_id` | VARCHAR(100) | Composite FK, see below |
| `frequency` | INTEGER | Count in that specific exam |
| `in_official_wordlist` | BOOLEAN | |
| `created_at` | TIMESTAMPTZ | |

Unique constraint: `(word, source_type, exam_id)`
Foreign key: `(exam_id, source_type)` → `exam_sources (exam_id, source_type)`
— composite, to match the fixed constraint above. Any query joining
`word_frequencies` to `exam_sources` must match on **both** columns
(`backend/routers/search.py` does this).

---

### `frequency_aggregates`

Pre-aggregated totals across all exams. Rebuilt on every ETL run.

Contains three rows per word: one for `reading`, one for `listening`, one for `all`.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `word` | VARCHAR(50) | |
| `hsk_level` | SMALLINT | |
| `source_type` | VARCHAR(20) | `reading`, `listening`, or `all` |
| `total_frequency` | INTEGER | Sum across all exams |
| `exam_count` | INTEGER | Number of distinct exams the word appeared in |
| `in_official_wordlist` | BOOLEAN | |
| `updated_at` | TIMESTAMPTZ | |

Unique constraint: `(word, source_type)`

---

### `exam_sentences`

Example sentences extracted from `data/raw/raw_extractions.parquet`, one row
per cleaned, deduplicated sentence per exam file. Powers the example-sentence
list in `GET /api/search/word-detail`.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `exam_id` | VARCHAR(100) | Composite FK, see below |
| `source_type` | VARCHAR(20) | `reading` or `listening` |
| `sentence` | TEXT | Cleaned sentence text |
| `created_at` | TIMESTAMPTZ | |

Unique constraint: `(exam_id, source_type, sentence)`
Foreign key: `(exam_id, source_type)` → `exam_sources (exam_id, source_type)`

Populated by `etl/load_sentences.py`, which is fully rerunnable — it deletes
and reloads the whole table each run rather than upserting incrementally, so
re-running it after regenerating `raw_extractions.parquet` is always safe.
See [ETL Pipeline](etl-pipeline.md#load_sentencespy) for the cleaning rules
(question numbers, option letters, fill-in-the-blank markers, and
exam-boilerplate sentences shared across 3+ papers are all stripped before
insert).

---

## Indexes

| Index | Table | Column(s) | Purpose |
|---|---|---|---|
| `idx_wf_word` | word_frequencies | word | Word lookup |
| `idx_wf_hsk_level` | word_frequencies | hsk_level | Level filter |
| `idx_wf_source_type` | word_frequencies | source_type | Source filter |
| `idx_fa_hsk_level` | frequency_aggregates | hsk_level | API level filter |
| `idx_fa_source_type` | frequency_aggregates | source_type | API source filter |
| `idx_fa_total_freq` | frequency_aggregates | total_frequency DESC | Top-N queries |

---

## Entity Relationship

```
hsk_wordlist ──(join on word)── word_frequencies ──► frequency_aggregates
                                       │
                                       ▼
                                 exam_sources ──◄── exam_sentences
```

`word_frequencies (exam_id, source_type)` → `exam_sources (exam_id, source_type)` (composite FK)
`frequency_aggregates` is a materialized-style summary; it's rebuilt from
`word_frequencies` once per ETL batch (`etl.load_to_db.refresh_aggregates`),
not per-exam — an earlier version rebuilt it after every single exam insert,
which meant a full-table `GROUP BY` scan 130 times over during a full load.

---

## Connecting Manually

```bash
# via docker compose
docker compose exec db psql -U hsk_user -d hsk_frequency

# useful queries
SELECT word, total_frequency FROM frequency_aggregates
WHERE hsk_level = 4 AND source_type = 'all'
ORDER BY total_frequency DESC LIMIT 20;

SELECT word, COUNT(DISTINCT exam_id) as exam_count
FROM word_frequencies
WHERE in_official_wordlist = FALSE
GROUP BY word ORDER BY exam_count DESC LIMIT 20;
```
