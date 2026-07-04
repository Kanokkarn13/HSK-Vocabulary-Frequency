# API Endpoints

Base URL (local): `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
OpenAPI JSON: `http://localhost:8000/openapi.json`

CORS only allows origins listed in the `CORS_ALLOW_ORIGINS` env var (comma-separated,
defaults to `http://localhost:5173` — the frontend dev server), and only `GET`
requests, since every route here is read-only.

---

## GET `/health`

Health check.

**Response:**
```json
{ "status": "ok" }
```

---

## GET `/api/frequency/top`

Top N most frequent words, with optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hsk_level` | int (1–9) | null | Filter by the word's own official HSK level |
| `exam_level` | int (1–9) | null | Filter by the HSK level of the exam **paper itself** (e.g. 3 or 4) — independent of `hsk_level`. Bypasses the pre-aggregated `frequency_aggregates` table and joins `word_frequencies`+`exam_sources` live, since aggregates have no per-exam-level dimension |
| `exam_id` | string | null | Restrict to one specific exam. Reading and listening counts for that exam are automatically combined (the `source_type` param is ignored when this is set) |
| `source_type` | string | `all` | `reading`, `listening`, or `all` |
| `limit` | int (1–10,000) | 50 | Number of results returned. Raised to 10,000 (from an earlier 500) so the frontend can fetch the entire matching list for its searchable table |

**Example:**

```
GET /api/frequency/top?hsk_level=4&source_type=reading&limit=20
GET /api/frequency/top?exam_level=3&limit=10000
GET /api/frequency/top?exam_id=H31001
```

**Response:**
```json
{
  "items": [
    {
      "word": "学生",
      "hsk_level": 1,
      "source_type": "reading",
      "total_frequency": 47,
      "exam_count": 12,
      "in_official_wordlist": true
    }
  ],
  "count": 20,
  "total_count": 7587
}
```

`count` is `items.length` (capped by `limit`); `total_count` is the full
number of matching rows regardless of `limit` — use it for "N of M" UI, not `count`.

---

## GET `/api/frequency/exams`

List of exams, with each exam's reading and listening entries merged into a
single row (they share the same `exam_id`). Powers the frontend's exam picker.

**Response:**
```json
{
  "items": [
    { "exam_id": "H30000", "hsk_level": 3, "year": null, "source_types": ["listening", "reading"] }
  ],
  "count": 65
}
```

---

## GET `/api/search/word`

Look up a specific word and see all its occurrences.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `q` | string | yes | Chinese word to search |

**Example:**

```
GET /api/search/word?q=学习
```

**Response:**
```json
{
  "word": "学习",
  "aggregates": [
    {
      "word": "学习",
      "hsk_level": 2,
      "source_type": "all",
      "total_frequency": 31,
      "exam_count": 9,
      "in_official_wordlist": true
    }
  ],
  "occurrences": [
    {
      "word": "学习",
      "hsk_level": 2,
      "source_type": "reading",
      "exam_id": "H31001",
      "frequency": 4,
      "in_official_wordlist": true,
      "year": null,
      "filename": "H31001.pdf"
    }
  ]
}
```

---

## GET `/api/compare/wordlist-vs-actual`

Compare official HSK wordlist against what actually appears in exams.

> Not currently called by the frontend (see [wiki/frontend.md](frontend.md#known-gaps--non-goals))
> — the main word table's search + "in HSK?" data covers the same need now.
> Kept as a standalone API capability.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hsk_level` | int (1–9) | null | Filter by the word's own HSK level |
| `exam_level` | int (1–9) | null | Filter by the exam paper's HSK level (same semantics as `/top`) |
| `exam_id` | string | null | Restrict to one specific exam (reading+listening combined) |
| `source_type` | string | `all` | `reading`, `listening`, or `all` |
| `limit` | int (1–500) | 50 | Results per category |

**Example:**

```
GET /api/compare/wordlist-vs-actual?hsk_level=4
```

**Response:**
```json
{
  "not_in_official_wordlist": [
    {
      "word": "网络",
      "hsk_level": null,
      "total_frequency": 23,
      "exam_count": 7
    }
  ],
  "in_official_wordlist": [
    {
      "word": "学生",
      "hsk_level": 1,
      "total_frequency": 47,
      "exam_count": 12,
      "pinyin": "xué shēng"
    }
  ]
}
```

Use `not_in_official_wordlist` to find vocabulary that appears frequently in real exams but isn't on the official list — these are high-value words to study that official lists miss.

---

## Error Responses

| Status | Meaning |
|---|---|
| 422 | Validation error (invalid query params) |
| 500 | Internal server error (check DB connection) |

Error body follows FastAPI's default format:
```json
{
  "detail": [
    { "loc": ["query", "hsk_level"], "msg": "value is not a valid integer", "type": "type_error.integer" }
  ]
}
```
