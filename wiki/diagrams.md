# Diagrams

Mermaid diagrams for the shapes of this system that are easier to see than to
read in prose. Rendered automatically by GitHub in this file. Source tables/
flows: [Database Schema](database-schema.md), [ETL Pipeline](etl-pipeline.md),
[DevSecOps Pipeline](devsecops.md), [Frontend Dashboard](frontend.md),
[Deploying to Vercel + Neon](deploy-vercel.md).

---

## Entity Relationship Diagram

```mermaid
erDiagram
    HSK_WORDLIST {
        int id PK
        string word UK "simplified Chinese"
        string pinyin
        smallint hsk_level "1-9"
        text definition "English gloss"
        text definition_th "Thai gloss"
        timestamptz created_at
    }

    EXAM_SOURCES {
        int id PK
        string exam_id "e.g. H31001, not unique alone"
        smallint year
        string source_type "reading | listening"
        smallint hsk_level "the exam paper's own level, nullable"
        string filename
        timestamptz processed_at
    }

    WORD_FREQUENCIES {
        int id PK
        string word
        smallint hsk_level "from wordlist join, nullable"
        string source_type "reading | listening"
        string exam_id
        int frequency
        boolean in_official_wordlist
        timestamptz created_at
    }

    FREQUENCY_AGGREGATES {
        int id PK
        string word
        smallint hsk_level
        string source_type "reading | listening | all"
        int total_frequency
        int exam_count
        boolean in_official_wordlist
        timestamptz updated_at
    }

    EXAM_SENTENCES {
        int id PK
        string exam_id
        string source_type "reading | listening"
        text sentence "cleaned, deduplicated"
        timestamptz created_at
    }

    EXAM_SOURCES ||--o{ WORD_FREQUENCIES : "(exam_id, source_type) FK"
    EXAM_SOURCES ||--o{ EXAM_SENTENCES : "(exam_id, source_type) FK"
    HSK_WORDLIST ||--o{ WORD_FREQUENCIES : "word match, app-level (no FK)"
    WORD_FREQUENCIES ||--o{ FREQUENCY_AGGREGATES : "rebuilt from, app-level (no FK)"
```

Notes:
- `word_frequencies` and `exam_sentences` both key off the **composite**
  `(exam_id, source_type)`, not `exam_id` alone — see the "Fixed bug" note in
  [Database Schema](database-schema.md#exam_sources) for why that constraint
  shape matters.
- The `hsk_wordlist → word_frequencies` and `word_frequencies →
  frequency_aggregates` links are logical, not enforced foreign keys —
  `frequency_aggregates` is a full-table rebuild
  (`etl.load_to_db.refresh_aggregates`), not a live join.

---

## System Architecture

```mermaid
flowchart LR
    subgraph Client["Browser"]
        SPA["React 19 SPA\nVite + TS + Tailwind"]
    end

    subgraph Vercel["Vercel (one project, free Hobby tier)"]
        Static["Static frontend build\n(frontend/dist)"]
        API["FastAPI — single Python function\n(api/index.py -> backend/main.py)\nSlowAPI rate limit, UA-scraper block, CORS"]
    end

    subgraph Neon["Neon — serverless Postgres 16"]
        DB[("neondb\npooled endpoint (pgbouncer)")]
    end

    subgraph Local["Local machine (manual, one-time / on data refresh)"]
        Notebooks["notebooks/01, 02\n(extract text, segment + count)"]
        Loaders["etl/load_word_counts.py\netl/load_sentences.py"]
    end

    SPA -- HTTPS --> Static
    SPA -- "/api/*, /health (same origin)" --> API
    API -- "psycopg2, NullPool\n(pooled connection string)" --> DB
    Notebooks --> Loaders
    Loaders -- "psycopg2\n(direct, non-pooled connection string)" --> DB

    UptimeRobot["UptimeRobot\n(5-min poll)"] -. "GET /health" .-> API
```

---

## ETL Pipeline

```mermaid
flowchart TD
    A["Exam files\n(PDFs + audio)"] --> B["notebooks/01_extract_raw_text.ipynb"]
    B --> B1["pdfplumber + PaddleOCR fallback\n(PDF -> text)"]
    B --> B2["Whisper, lang=zh\n(audio -> text)"]
    B --> B3["Completeness validation\nper file type"]
    B --> B4["HSK wordlist snapshot\n(external API)"]
    B1 --> C1[("data/raw/raw_extractions.parquet")]
    B2 --> C1
    B4 --> C2[("data/processed/hsk_wordlist.csv")]

    C1 --> D["notebooks/02_segment_and_count.ipynb"]
    C2 --> D
    D --> D1["Dedupe repeated audio sentences"]
    D --> D2["Traditional to simplified (opencc)"]
    D --> D3["jieba segmentation + CJK filter"]
    D --> D4["Join wordlist -> label level"]
    D --> D5["Fallback: decompose unmatched compounds"]
    D --> D6["Cross-check remainder vs CC-CEDICT"]
    D6 --> E[("data/processed/word_counts.parquet")]

    C1 --> F["etl/load_sentences.py\n(clean + dedupe + boilerplate filter)"]
    F --> G[("exam_sentences table")]

    E --> H["etl/load_word_counts.py"]
    C1 --> H
    C2 --> H
    H --> H1["upsert hsk_wordlist"]
    H --> H2["upsert exam_sources"]
    H --> H3["upsert word_frequencies\nper (exam_id, source_type)"]
    H3 --> H4["refresh_aggregates()\nfull rebuild, once at the end"]

    H1 --> I[("PostgreSQL")]
    H2 --> I
    H4 --> I
    G --> I

    I --> J["FastAPI (backend/)"]
    J --> K["React dashboard (frontend/)"]
```

---

## DevSecOps / CI-CD Pipeline

```mermaid
flowchart TD
    Trigger(["Push to master/develop,\nor PR into master"]) --> Test

    subgraph Test["Test job"]
        T1["Spin up postgres:16-alpine\nservice container"]
        T2["pytest tests/ --cov=backend --cov=etl"]
        T1 --> T2
    end

    Test -->|success| Security

    subgraph Security["Security & Quality Scan job"]
        S1["Bandit SAST\n(backend/, etl/)"]
        S2["Coverage run (for SonarCloud input)"]
        S3["SonarCloud scan"]
        S1 --> S2 --> S3
    end

    Security -->|success| Terraform

    subgraph Terraform["IaC Syntax Check job"]
        F1["terraform fmt -check"]
        F2["terraform init"]
        F3["terraform validate"]
        F1 --> F2 --> F3
    end

    Terraform -.->|"no plan/apply in CI\n(state is local-only)"| Done(["No CI deploy job"])
    Done -.-> VercelDeploy["Vercel's native GitHub integration\n(preview per PR, prod on push to master)"]
```

---

## Request Sequence — `GET /api/search/word-detail`

The endpoint behind the word-detail modal (see
[Frontend Dashboard](frontend.md#word-detail-modal) and
[API Endpoints](api-endpoints.md)), and the one hit by the 2026-07-07 production
500 (schema drift between local Docker Postgres and Neon — see the README's
"Known bug" note).

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant FE as React SPA
    participant MW as FastAPI middleware
    participant API as word_detail() handler
    participant DB as Postgres (Neon)

    U->>FE: Click a word row
    FE->>MW: GET /api/search/word-detail?q=<word>
    MW->>MW: Block known-scraper User-Agent
    MW->>MW: SlowAPI rate limit (60/min)
    MW->>API: forward request
    API->>DB: SELECT word, pinyin, hsk_level,\ndefinition, definition_th\nFROM hsk_wordlist WHERE word = :word
    DB-->>API: 0 or 1 row
    API->>DB: SELECT COUNT(DISTINCT sentence),\nCOUNT(DISTINCT (exam_id, source_type))\nFROM exam_sentences WHERE sentence LIKE :pattern
    DB-->>API: sentence_total, file_total
    API->>DB: nested DISTINCT ON query:\ndedupe by sentence, then by (exam_id, source_type),\nJOIN exam_sources, ORDER BY closeness to 20 chars, LIMIT 10
    DB-->>API: up to 10 example sentences
    API-->>FE: 200 JSON {pinyin, definition, definition_th,\nsentence_total, file_total, sentences[]}
    FE-->>U: Render modal
```

---

## Frontend Data Flow

```mermaid
flowchart TD
    App["App.tsx\n(filter state: hskLevel, sourceType, examLevel, examId)"]
    App -->|"GET /api/frequency/top\n(limit up to 10,000)"| API1["FastAPI /api/frequency"]
    API1 --> App

    App --> Chart["TopWordsChart\n(top 15, Recharts)"]
    App --> Stats["StatCard strip"]
    App --> Table["TopWordsTable\n(client-side search + pagination,\nfilters out rows with no hsk_level)"]

    Table -->|"click a row"| Modal["WordDetailModal"]
    Modal -->|"GET /api/search/word-detail?q=..."| API2["FastAPI /api/search"]
    API2 --> Modal

    FilterBar["FilterBar\n(top of page + floating button\nvia IntersectionObserver)"] --> App
    Chips["ActiveFilterChips\n(above table, always visible)"] --> App
```
