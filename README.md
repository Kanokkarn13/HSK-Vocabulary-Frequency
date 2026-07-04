# HSK Vocabulary Frequency Analyzer

A Data Engineering + DevSecOps portfolio project that analyzes word frequency across old HSK exam papers (reading and listening), then compares results against the official HSK wordlist to surface which words actually appear most often in real exams.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Data Sources                                │
│  PDF (reading exams)              Audio files (listening exams)      │
└────────────┬──────────────────────────────┬─────────────────────────┘
             │                              │
             ▼                              ▼
      pdfplumber                     OpenAI Whisper
      (text layer)                   (local STT, lang=zh)
             │
    has text? ──no──▶ PaddleOCR (OCR fallback)
             │         (sparse <150 c/page → OCR)
             │         (cid artifacts >10 → OCR)
             │
             └──────────────┬────────────────┘
                            ▼
                  notebooks/01_extract_raw_text.ipynb
                  - Inventory + dedup (130 files → 65 unique)
                  - Completeness validation per file type
                  - Saves: data/raw/raw_extractions.parquet
                            │
                            ▼
                  HSK Wordlist API snapshot
                  (X-API-KEY, page/per_page pagination)
                  - Saves: data/processed/hsk_wordlist.parquet
                            │
                            ▼
                  notebooks/02_segment_and_count.ipynb
                  - Dedupe repeats + simplify (T2S) + jieba segmentation
                  - Join hsk_word_level_lookup.csv, fallback-decompose
                    unmatched compounds (numerals, verbs, pronouns, ...)
                  - Cross-check remaining gaps against CC-CEDICT
                  - 95.5% of token occurrences matched an HSK level
                  - Saves: data/processed/word_counts.parquet
                            + unmatched_words_review.csv / _in_cedict.csv
                            │
                            ▼
                  etl/load_word_counts.py
                  - Bridges notebook output → Postgres
                  - Upserts hsk_wordlist, exam_sources,
                    word_frequencies, then rebuilds
                    frequency_aggregates once per batch
                            │
                            ▼
                  PostgreSQL (new DB)
                  hsk_wordlist │ exam_sources
                  word_frequencies │ frequency_aggregates
                            │
                            ▼
                  FastAPI REST API
                  /api/frequency (top, exams) /api/search /api/compare
                            │
                            ▼
                  React Frontend Dashboard
                  filters, chart, searchable/paginated
                  table — frontend/ (Vite + TS + Tailwind)
```

## Tech Stack

| Layer | Technology |
|---|---|
| ETL (Notebooks) | Python, pdfplumber, PaddleOCR 2.8.1, OpenAI Whisper, jieba, OpenCC, CC-CEDICT |
| ETL → DB bridge | `etl/load_word_counts.py`, `etl/load_to_db.py` (SQLAlchemy upserts), `etl/logging_config.py` |
| API | FastAPI, SQLAlchemy |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS v4, Recharts, axios |
| Database | PostgreSQL 16 |
| Container | Docker, Docker Compose (local dev only) |
| CI/CD | GitHub Actions |
| IaC | Terraform (Vercel + Neon) |
| Security | Bandit (SAST), SonarCloud (quality + hotspots), Dependabot (dependency CVEs + auto-update PRs) |
| Cloud | Vercel (hosting), Neon (serverless Postgres) — all free tier |
| Monitoring | UptimeRobot |

---

## Project Structure

```
HSK-Vocabulary-Frequency/
├── notebooks/
│   ├── 01_extract_raw_text.ipynb    # PDF/audio extraction + wordlist API
│   ├── 01b_whisper_colab.ipynb      # Colab clone of the Whisper step (GPU)
│   └── 02_segment_and_count.ipynb   # jieba segmentation + HSK labeling
├── data/
│   ├── raw/
│   │   └── raw_extractions.parquet # Text per file (PDF + Whisper transcripts, 130 rows)
│   ├── external/                   # Third-party reference data (gitignored, downloaded on demand)
│   │   └── cedict_ts.u8            # CC-CEDICT dictionary (MDBG, CC BY-SA 4.0)
│   └── processed/
│       ├── hsk_wordlist.parquet    # Wordlist snapshot from API
│       ├── hsk_wordlist.csv        # Same, utf-8-sig CSV
│       ├── hsk_word_level_lookup.csv  # word → level (for labeling)
│       ├── word_counts.parquet     # Frequency per word per exam (102,315 rows, 95.5% matched)
│       ├── unmatched_words_review.csv     # Unmatched words + triage signals
│       └── unmatched_words_in_cedict.csv  # Unmatched words CC-CEDICT confirms are real
├── backend/                        # FastAPI application
│   ├── main.py                     # CORS (CORS_ALLOW_ORIGINS env var), router mounting
│   ├── db.py
│   └── routers/
│       ├── frequency.py            # GET /api/frequency/top, /exams
│       ├── search.py               # GET /api/search/word, /word-detail
│       └── compare.py              # GET /api/compare/wordlist-vs-actual
├── frontend/                       # React dashboard (Vite + TypeScript + Tailwind CSS v4)
│   ├── src/
│   │   ├── App.tsx                 # Page layout, filter state, data fetching, floating filter button
│   │   ├── api/                    # client.ts (axios) + types.ts
│   │   ├── components/             # Navbar, FilterBar, ActiveFilterChips, TopWordsChart/Table,
│   │   │                           # WordDetailModal, SearchPanel, ErrorBoundary, icons.tsx
│   │   ├── hooks/useAsync.ts        # Shared async-fetch state hook + error sanitization
│   │   └── index.css               # Design tokens (brand/ink color scales, fonts)
│   └── .env.example                # VITE_API_BASE_URL
├── etl/
│   ├── pipeline.py                 # CLI entry point for raw PDF/audio → DB (one exam at a time)
│   ├── extract_pdf.py
│   ├── transcribe_audio.py
│   ├── segment_and_count.py
│   ├── load_to_db.py               # Upsert primitives (wordlist, exam_sources, frequencies, aggregates)
│   ├── load_word_counts.py         # Bridges notebook output (parquet) → Postgres, run after notebooks 01/02
│   ├── load_sentences.py           # Extracts/loads example sentences into exam_sentences (rerunnable)
│   └── logging_config.py           # Shared logging.Logger setup (no print())
├── db/
│   └── schema.sql
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.etl
├── .github/
│   └── workflows/
│       └── ci-cd.yml
├── infra/
│   └── main.tf                      # Terraform: Vercel + Neon (free tier)
├── sonar-project.properties
├── requirements/
│   ├── api.txt
│   └── etl.txt
├── tests/
│   └── test_segment.py
├── wiki/                           # Detailed documentation
├── .env.example
└── docker-compose.yml
```

---

## Quick Start (Local — Notebook Workflow)

### Prerequisites

- Python 3.11+
- `C:\ml-env` virtual environment with OCR/Whisper packages (see [wiki/setup.md](wiki/setup.md))
- Exam PDFs + audio files (see [wiki/data-sourcing.md](wiki/data-sourcing.md))
- `.env` with `HSK_WORDLIST_API_URL` and `HSK_WORDLIST_API_KEY`

### 1. Configure environment

```powershell
cp .env.example .env
# Edit .env — set HSK_WORDLIST_API_URL and HSK_WORDLIST_API_KEY
```

### 2. Register Jupyter kernel

```powershell
C:\ml-env\Scripts\python.exe -m ipykernel install --user --name ml-env --display-name "Python (ml-env)"
```

### 3. Run notebook 01

Open `notebooks/01_extract_raw_text.ipynb` in VS Code.  
Select kernel: **Python (ml-env)**  
Run all cells. (No local GPU? Run the Whisper step in Colab instead — see `notebooks/01b_whisper_colab.ipynb`.)

Outputs:
- `data/raw/raw_extractions.parquet` — extracted text per file (130 rows: 65 reading + 65 listening)
- `data/processed/hsk_wordlist.parquet` — wordlist snapshot from API (7,410 words, levels 1-6, as of 2026-07-03)
- `data/processed/hsk_word_level_lookup.csv` — word → HSK level mapping

> **Cache note:** the wordlist cell only re-fetches from the API when `FORCE_REFRESH = True` or no snapshot exists yet — set it to `True` and re-run if the source wordlist has changed since your last snapshot, then set it back to `False`. The API itself caches from Supabase via a debounced webhook, so a freshly-added word can take a short while to show up even with `FORCE_REFRESH = True`.

> **License check:** Verify you have the right to use any exam material before adding it. See [wiki/data-sourcing.md](wiki/data-sourcing.md).

### 3b. Run notebook 02

Open `notebooks/02_segment_and_count.ipynb`, select kernel **Python (ml-env)**, run all cells. Downloads CC-CEDICT (~4MB, cached after first run) for the unmatched-word cross-check.

Outputs:
- `data/processed/word_counts.parquet` — one row per (word, exam_id, source_type) with `level` (direct wordlist match), `effective_level` (direct + pattern-decomposed), and `match_type`/`match_pattern` columns. 95.5% of token occurrences matched an HSK level (85.9% direct + 9.6pp from decomposition).
- `data/processed/unmatched_words_review.csv` / `unmatched_words_in_cedict.csv` — words not in the HSK wordlist, for optional follow-up on the wordlist source (see [wiki/etl-pipeline.md](wiki/etl-pipeline.md)).

### 4. Load the results into Postgres

```bash
docker compose up -d db
python -m etl.load_word_counts
```

This reads `data/processed/word_counts.parquet`, `hsk_wordlist.csv`, and
`data/raw/raw_extractions.parquet`, and upserts everything into
`hsk_wordlist`, `exam_sources`, `word_frequencies`, then rebuilds
`frequency_aggregates` once. Safe to re-run after re-running notebooks 01/02.

```bash
python -m etl.load_sentences
```

Extracts example sentences from `raw_extractions.parquet` into
`exam_sentences`, powering the word-detail lookup's example sentences (see
[wiki/etl-pipeline.md](wiki/etl-pipeline.md#load_sentencespy)). Independent
of the step above — run it any time `raw_extractions.parquet` changes.

### 5. Run the API

```bash
docker compose up -d api
# or locally: uvicorn backend.main:app --reload --port 8000
```

API available at: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

### 6. Run the frontend dashboard

```bash
cd frontend
cp .env.example .env   # set VITE_API_BASE_URL if the API isn't on localhost:8000
npm install
npm run dev
```

Dashboard available at: `http://localhost:5173`

---

## API Reference

| Endpoint | Description |
|---|---|
| `GET /api/frequency/top` | Top N most frequent words, each including `pinyin`. Params: `hsk_level` (word's level), `exam_level` (level of the exam paper), `exam_id` (one or more specific exams), `source_type` (reading/listening/all — combines freely with `exam_id`/`exam_level`), `limit` (up to 10,000). Response includes `total_count`, the full match count regardless of `limit` |
| `GET /api/frequency/exams` | List of exams (reading + listening merged into one entry per `exam_id`) — powers the frontend's exam picker |
| `GET /api/search/word?q=你好` | Frequency breakdown for a single word across all exams |
| `GET /api/search/word-detail?q=你好` | Pinyin, EN/TH definitions, and up to 10 example sentences (with source exam files) for one word — powers the frontend's click-to-expand word modal |
| `GET /api/compare/wordlist-vs-actual` | Words in exams NOT in official wordlist, and official words ranked by exam frequency. Not currently used by the frontend (see [wiki/frontend.md](wiki/frontend.md)), kept as a standalone API capability |
| `GET /health` | Health check |

CORS is restricted to origins listed in the `CORS_ALLOW_ORIGINS` env var (defaults to `http://localhost:5173`). The API also rate-limits to 60 req/min per IP and blocks requests with no/known-scraper User-Agent strings (`backend/main.py`) — best-effort, in-memory deterrents against casual scraping, not a hard guarantee. `frontend/public/robots.txt` disallows crawling `/api/*`.

Full parameter docs: `http://localhost:8000/docs`

---

## Running Tests

```bash
pip install -r requirements/api.txt -r requirements/etl.txt pytest httpx
pytest tests/ -v
```

---

## Development Phases

| Phase | Status | Description |
|---|---|---|
| 1 — Data Prep | ✅ Complete | 130 files inventoried, 65 PDFs extracted (pdfplumber + PaddleOCR), wordlist API integrated (7,410 words, levels 1-6) |
| 2 — Audio Processing | ✅ Complete | Whisper medium, 65/65 audio files transcribed, merged into `raw_extractions.parquet` (130 rows) |
| 3 — ETL Core | ✅ Complete | `02_segment_and_count.ipynb` — jieba + HSK labeling + fallback decomposition (numerals, verbs, pronouns, measure words, aspect particles, ...) + CC-CEDICT cross-check → `word_counts.parquet` (102,315 rows, **95.5%** of occurrences / 61.2% of unique words matched to an HSK level) |
| 4 — API | ✅ Complete | 5 FastAPI endpoints backed by a real Postgres database (`etl/load_word_counts.py` loads 7,587 words / 130 exams / 102,315 frequency rows; `etl/load_sentences.py` loads ~20,400 example sentences), verified end-to-end from the frontend |
| 5 — Frontend | ✅ Complete | React + Vite + TypeScript + Tailwind dashboard — filters (word HSK level, exam-paper level, specific exam, source type) with a scroll-following floating filter button + removable filter chips, top-15 chart, searchable/paginated full word table with pinyin (search matches pinyin too), click-to-expand word detail modal (definitions + example sentences from real exams), word lookup panel, dark mode, error boundary. See [wiki/frontend.md](wiki/frontend.md) |
| 6 — DevSecOps | 🟡 In progress | Docker (local dev only), GitHub Actions (Test → Security → IaC), Terraform (Vercel + Neon — project provisioned, schema + data loaded into Neon), Dependabot, SonarCloud. Pipeline being finalized in [PR #13](https://github.com/Kanokkarn13/HSK-Vocabulary-Frequency/pull/13); UptimeRobot monitor not yet configured |
| 7 — Portfolio | 🔲 Not started | Architecture diagram, demo video |

---

## Constraints

- **No live DB connection** to the flashcard app — wordlist is fetched via API snapshot (snapshot-only, not a live query during analysis).
- **License check** all exam PDFs and audio before use.
- **Whisper runs locally** during dev/test. Cloud STT is a later option if accuracy is insufficient.

---

## Deployment

Single target, entirely free tier: **Vercel** (serverless Python function,
native ASGI, no adapter needed + static frontend, same project) backed by
**Neon** (serverless Postgres). Provisioned via Terraform in
[`infra/main.tf`](infra/main.tf); once linked, Vercel's own GitHub
integration auto-deploys on every push to `master` (and a preview build per PR)
with no extra CI stage needed.

**Current status:** the Neon project and Vercel project both exist (created
via `terraform apply`), the schema is applied, and all 130 exams'
word-frequency data is loaded into Neon. Changes land through a PR into
`master` rather than a direct push, so both the GitHub Actions pipeline and
Vercel's preview deploy run against every change before it's live.

> **Migration note:** the `definition`/`definition_th` columns and
> `exam_sentences` table (word-detail feature, 2026-07-04) were only applied
> and loaded against the local Docker Postgres so far. Before this reaches
> Neon, run the updated `db/schema.sql` against Neon, then
> `load_wordlist_csv()` (for definitions) and `python -m etl.load_sentences`
> (for example sentences) with `DB_HOST`/etc pointed at Neon — otherwise
> `/api/search/word-detail` will error in production.

See [Deploying to Vercel + Neon](wiki/deploy-vercel.md) for full setup steps
and [DevSecOps Pipeline](wiki/devsecops.md) for the CI/CD + IaC pipeline.

---

## Wiki

Detailed documentation is in the [`wiki/`](wiki/) directory:

- [Setup Guide](wiki/setup.md)
- [ETL Pipeline](wiki/etl-pipeline.md)
- [Database Schema](wiki/database-schema.md)
- [API Endpoints](wiki/api-endpoints.md)
- [Frontend Dashboard](wiki/frontend.md)
- [Data Sourcing & Licensing](wiki/data-sourcing.md)
- [DevSecOps Pipeline](wiki/devsecops.md)
- [Deploying to Azure](wiki/azure-deploy.md)
- [Deploying to Vercel + Neon](wiki/deploy-vercel.md)
