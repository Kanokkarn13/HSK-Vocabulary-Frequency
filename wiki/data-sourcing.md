# Data Sourcing & Licensing

## HSK Wordlist

**Source:** REST API from the flashcard application.

**Rules:**
- Fetch a one-time snapshot — **never a live connection during analysis**.
- The wordlist is your own data; no third-party license issues.
- Re-fetch whenever the wordlist changes significantly (e.g., after a major vocabulary update).

**API details:**

| Setting | Value |
|---|---|
| Env var | `HSK_WORDLIST_API_URL` |
| Auth | `X-API-KEY` header (value from `HSK_WORDLIST_API_KEY`) |
| Pagination | `page` (1-based) / `per_page` (max 1000) query params — **not** `skip`/`limit` |
| Response | `{"metadata": {total_records, total_pages, page, per_page, has_next, has_previous}, "data": [...]}` |

**Pagination approach** — the notebook pages via `page`/`per_page` and stops using `metadata.has_next` (confirmed against the API's `/openapi.json`: total 7,410 words across 8 pages at `per_page=1000`, as of the 2026-07-03 snapshot). Sending `skip`/`limit` silently returns page 1 every time since the API ignores unknown query params:

```python
all_records, seen_ids, page = [], set(), 1
while True:
    resp = requests.get(api_url, headers={"X-API-KEY": api_key},
                        params={"page": page, "per_page": 1000}, timeout=30)
    raw = resp.json()
    records, metadata = raw["data"], raw["metadata"]
    new = [r for r in records if r.get("id") not in seen_ids]
    seen_ids.update(r["id"] for r in new)
    all_records.extend(new)
    if not metadata.get("has_next"):
        break
    page += 1
```

Note: `/words/{level}` only accepts levels 1–6, so "Missing levels" warnings for 7–9 in the notebook output reflect the source data, not a bug.

**Caching (two layers, both can hide new words):**
1. **Notebook side:** the fetch cell skips the API entirely and reloads the local `hsk_wordlist.parquet` snapshot unless `FORCE_REFRESH = True` (or no snapshot exists yet). Re-running the notebook without flipping this flag will look up-to-date but is actually just replaying the old snapshot.
2. **API side:** the API is FastAPI over Supabase with a webhook-driven in-memory/SQLite cache (`/webhook/supabase`, ~10s debounce). `GET /health` returns `cache_records` — compare it against the notebook's fetched total to confirm the API's own cache has caught up with Supabase before assuming a fetch is complete. Observed lag: cache read 5,343 words on 2026-07-02, then 7,410 on 2026-07-03 after the same underlying Supabase data had already been updated — i.e., words that were genuinely added didn't show up in the API immediately.

Current wordlist snapshot (2026-07-03): **7,410 words** — L1=497, L2=758, L3=962, L4=1003, L5=1317, L6=2872.

**Output files:**

| File | Purpose |
|---|---|
| `data/processed/hsk_wordlist.parquet` | Full snapshot (all fields) |
| `data/processed/hsk_wordlist.csv` | Same, utf-8-sig for Excel compatibility |
| `data/processed/hsk_word_level_lookup.csv` | `word`, `level` only — used for labeling in notebook 02 |

---

## CC-CEDICT (Reference Dictionary)

**Source:** [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict), a community-maintained Chinese-English dictionary published by MDBG.

**License:** CC BY-SA 4.0 (attribution + share-alike). Because of the share-alike term, the raw dictionary file is **not committed to the repo** — `notebooks/02_segment_and_count.ipynb` downloads it on first run and caches it at `data/external/cedict_ts.u8`, which is gitignored (see `data/external/` in `.gitignore`). Anyone cloning the repo gets a fresh copy from MDBG directly rather than a redistributed copy from this project.

**Usage:** cross-checking words that don't match the HSK wordlist, to distinguish real (but non-HSK) Chinese vocabulary from ASR/OCR noise. Not used for segmentation — see [wiki/etl-pipeline.md](etl-pipeline.md) for why loading it into jieba as a supplementary dictionary was tried and reverted.

---

## HSK Exam Papers

> **Always verify the license of any exam material before adding it to this project.**

### What to avoid

- Official Hanban/NEEA published exam booklets — these are under strict copyright and redistribution is prohibited.
- Scanned PDFs from exam prep books without explicit open license.

### What is generally usable

| Source | Notes |
|---|---|
| Sample exams published by Hanban/NEEA as free downloads | Check their terms — some allow personal/educational use |
| Exam papers from university course materials released under open license | Confirm the course's license |
| Community-contributed exam reconstructions (e.g., from memory) | License depends on the platform — check per item |
| Your own notes or reconstructions from exams you sat | Personal data, no third-party IP issues |

### Recommended approach

1. Search for HSK sample tests on the official HSK website (hsk.neea.edu.cn) — they sometimes publish free sample tests.
2. Look for university open-course repositories that include HSK practice materials with explicit CC licenses.
3. If using a book, check whether the publisher has released digital versions under open license.

### Actual exam inventory

Exams are stored outside the repo at `C:\Users\callm\Downloads\hsk3-4 exam`. Inventory as of Phase 1:

| HSK level | Full exams | Instruction sheets | Total |
|---|---|---|---|
| HSK 3 | 33 | 33 | 66 |
| HSK 4 | 32 | 32 | 64 |
| **Total** | **65** | **65** | **130** |

Exam IDs follow regex `^(H([34])\d{4}[A-Z]?)` — e.g., `H31327`, `H41439`.

### Naming convention

Files in the exam directory use this pattern:

```
{exam_id}[-suffix].pdf
```

Examples: `H31327.pdf`, `H31327-exam-paper.pdf`, `H41439A.pdf`

The `-exam-paper` / `试卷` suffix identifies instruction sheet files (just the 注意/notice page, not the full exam).

Document the source for each file in a `data/SOURCES.md` file (not committed if the files themselves aren't).

---

## Audio Files

Same license rules apply. Additional considerations:

- Audio from official listening CDs bundled with textbooks — usually copyrighted.
- Audio published as part of free sample tests — check terms.
- If unsure, err on the side of not including the file; transcribe only what you own or have clear rights to.

Whisper produces a transcript (text), not a copy of the audio. If you transcribe a file locally and only store the text output, your legal exposure is lower — but this is not legal advice.

---

## Keeping This Project Portfolio-Safe

For a portfolio project shown publicly:

- Do not commit copyrighted exam PDFs or audio files to the repo.
- `.gitignore` already excludes `data/reading/`, `data/listening/`, `data/wordlist/*.csv` (except the example file), and `data/external/` (third-party reference data like CC-CEDICT, downloaded on demand rather than redistributed).
- Include the example wordlist CSV (`hsk_wordlist_EXAMPLE.csv`) and a note telling reviewers to supply their own data.
- In the README, document where to find usable exam material without distributing it yourself.
