# ETL Pipeline

## Overview

The pipeline currently runs as Jupyter notebooks in `notebooks/`. Each notebook produces Parquet/CSV files consumed by the next stage.

```
Exam files (PDFs + audio)
        │
        ▼
notebooks/01_extract_raw_text.ipynb
├── Inventory + dedup (135 raw → 130 unique → 65 PDF + 65 audio)
├── PDF extraction: pdfplumber + PaddleOCR fallback
├── Audio transcription: OpenAI Whisper (local, lang=zh)
├── Completeness validation per file type
├── HSK wordlist snapshot from API
└── Saves:
    ├── data/raw/raw_extractions.parquet
    ├── data/processed/hsk_wordlist.parquet
    ├── data/processed/hsk_wordlist.csv
    └── data/processed/hsk_word_level_lookup.csv
        │
        ▼
notebooks/02_segment_and_count.ipynb
├── Dedupe repeated audio sentences (listening only)
├── Convert traditional → simplified (T2S)
├── jieba segmentation + CJK-only filter
├── Join hsk_word_level_lookup.csv → label each word
├── Fallback: decompose unmatched compounds (numerals, verbs, pronouns, ...)
├── Cross-check remaining unmatched words against CC-CEDICT
└── Saves:
    ├── data/processed/word_counts.parquet
    ├── data/processed/unmatched_words_review.csv
    └── data/processed/unmatched_words_in_cedict.csv
        │
        ▼
etl/load_word_counts.py
├── Reads word_counts.parquet, hsk_wordlist.csv, raw_extractions.parquet
├── Upserts hsk_wordlist, exam_sources (skips malformed source rows,
│   e.g. a wordlist row with a non-Chinese "word" and no level — logged
│   as a warning, not fatal)
├── Upserts word_frequencies per (exam_id, source_type) group
└── Rebuilds frequency_aggregates once at the end (not per-exam)
        │
        ▼
PostgreSQL → FastAPI (backend/) → React dashboard (frontend/)
```

See [Database Schema](database-schema.md) and [Frontend Dashboard](frontend.md).

### `load_word_counts.py` vs `pipeline.py`

There are two separate ways to get data into Postgres, for two different
workflows:

- **`etl/load_word_counts.py`** — the one actually used. Bridges the
  notebook-based batch workflow (run notebooks 01 and 02, then this script)
  into the DB all at once. This is what the [Setup Guide](setup.md) and
  main [README](../README.md) Quick Start use.
- **`etl/pipeline.py`** — a CLI entry point (`python -m etl.pipeline
  --source-type reading --input-dir data/reading`) for adding *one exam at a
  time* straight from raw PDF/audio, without going through the notebooks.
  Useful for incrementally adding a single new exam later without re-running
  the full notebook batch. Both ultimately call the same upsert primitives
  in `etl/load_to_db.py`.

Both scripts log via `etl/logging_config.py` (a shared `logging.Logger`
setup with timestamps and levels) instead of `print()`.

---

## `load_sentences.py`

A third, independent loader (`python -m etl.load_sentences`) that populates
`exam_sentences` (see [Database Schema](database-schema.md#exam_sentences))
from `data/raw/raw_extractions.parquet` — the same source file
`load_word_counts.py` reads, but this script only needs the raw text, not
the segmented word counts, so it runs on its own rather than being folded
into that pipeline.

**Sentence splitting:** text is split on sentence-final punctuation
(`。！？!?；;`) and newlines (reading PDFs put each item on its own line).

**Cleaning** (`_clean_candidate`) strips exam scaffolding repeatedly until
stable, since noise stacks (e.g. `12．★ 他来北京6年了。` has both a question
number and a star marker):

- Leading question numbers (`12．`, `12.`), CJK ordinal numbers (`一,`)
- Leading option letters (`A `, `B、`)
- Stars, brackets, arrows, and other punctuation clusters
- The literal `例如` (exam "for example" prompts)

A candidate is then dropped entirely if it has fewer than 6 CJK characters,
is longer than 80 characters, is less than 60% CJK by character count (OCR
junk / English boilerplate), or still contains mid-sentence noise — a lone
option letter (`老朋友 B 不认识的字 C 爱好相同的人`, merged multi-choice options)
or an empty fill-in-the-blank bracket (`（ ）`).

**Boilerplate filter:** every exam paper prints identical instruction text
and `例如` sample sentences, so after cleaning all 130 files, any sentence
appearing in **3 or more different exams** is dropped as boilerplate before
insert — genuine content only ever repeats across at most a couple of exams
(HSK recycles some real questions).

**Fully rerunnable:** the script `DELETE`s the whole table and reloads it
every run rather than upserting incrementally, so it's always safe to re-run
after `raw_extractions.parquet` changes. Current output: ~20,400 sentences
across 130 files (from ~26,500 before the boilerplate filter).

---

## Notebook 01: Extract Raw Text

### Cell pipeline

| Cell | What it does |
|---|---|
| Imports + env | Load dotenv, set `EXAM_DIR`, `TEST_ONLY` flag |
| Inventory | Walk `EXAM_DIR`, parse exam ID with regex `^(H([34])\d{4}[A-Z]?)` |
| Dedup | Score duplicates (`_copy`, `-audio`, 试卷, `(1)` → higher score = drop) |
| Classify | `full_exam` vs `instruction_sheet` (exam-paper/试卷 files) |
| PDF extract | pdfplumber + 3-condition OCR fallback (see below) |
| Audio | Whisper, `language='zh'`. Can run locally (`small`, CPU-only machine) or via `01b_whisper_colab.ipynb` (`medium`, free T4 GPU — faster + better accuracy). 65/65 files transcribed `ok`. |
| Completeness | Validate section headers + question coverage per file type |
| HSK API | Snapshot wordlist from `HSK_WORDLIST_API_URL` |
| Save | raw_extractions.parquet, hsk_wordlist files |
| Plots | 3-panel matplotlib diagnostic figure |

### PDF extraction: 3-condition OCR fallback

`extract_pdf_text(filepath)` applies pdfplumber first, then falls back to PaddleOCR under any of these conditions:

| Condition | Result label |
|---|---|
| pdfplumber returns empty text | `ocr_ok` |
| `chars_per_page < 150` — sparse / scanned PDF | `sparse_then_ocr_ok` |
| More than 10 `(cid:N)` artifacts — broken font encoding | `cid_then_ocr_ok` |
| pdfplumber text is clean | `ok` |

Actual results across 65 PDFs:

| Method | Count |
|---|---|
| `ok` | 50 |
| `ocr_ok` | 9 |
| `sparse_then_ocr_ok` | 5 |
| `cid_then_ocr_ok` | 1 |

OCR uses `pymupdf` (fitz) to render each page to a numpy array at 200 DPI, then PaddleOCR 2.8.1 to extract text.

### Completeness validation

Two validation paths based on file type:

**`full_exam`** (main exam paper):
- Must have ≥ 3 section headers matching `第[一二三四五六七八九十]+部分`
- Question coverage must be ≥ 80% of the expected range (questions 1–N)

**`instruction_sheet`** (exam-paper / 试卷 files):
- Must contain `注意` (notice)
- Must contain at least two of: `听力`, `阅读`, `书写`
- Must contain at least one ordinal: `一`, `二`, `三`

Results: 48/48 full_exam passed, 17 instruction_sheet validated separately.

---

## Step 2: Segment and Count (`notebooks/02_segment_and_count.ipynb`)

### Pre-cleaning (before segmentation)

Three passes run on the listening (audio) text before it's tokenized:

1. **Dedupe repeated audio sentences.** HSK listening exams read every
   question twice, so raw Whisper transcripts contain each sentence
   back-to-back. Two sub-passes: an exact character-level repeat collapse
   (catches misaligned-prefix cases where Whisper glues noise onto only the
   first copy), then a fuzzy clause-level pass (`difflib.SequenceMatcher`
   ≥ 0.82, since the two plays of the same audio often transcribe slightly
   differently). Removed 30.4% of listening-text characters as repeats.
2. **Traditional → simplified (T2S)**, via `opencc` (`t2s` config). Some
   listening transcripts came out of Whisper in traditional characters even
   though the HSK wordlist and jieba's dictionary are both simplified.
3. **Segmentation + CJK-only filter** — tokenize with jieba, then drop any
   token containing a non-CJK character (`U+4E00–U+9FFF`) instead of
   partially cleaning it, same rule as `etl/segment_and_count.py`:

```python
_NON_CJK_RE = re.compile(r"[^一-鿿]")

def segment(text: str) -> list[str]:
    if not text:
        return []
    words = jieba.lcut(text)
    return [w for w in words if w and not _NON_CJK_RE.search(w)]
```

### Counting

Word frequencies are counted **per exam file**, not globally, so the output can
be aggregated by exam, HSK level, or source type downstream:

```python
rows = []
for _, r in df_raw.iterrows():
    for word, count in Counter(segment(r["text_clean"])).items():
        rows.append({"exam_id": r.exam_id, "hsk_level": r.hsk_level,
                      "source_type": r.source_type, "word": word, "count": count})
df_counts = pd.DataFrame(rows)
```

### HSK labeling

Join against `hsk_word_level_lookup.csv` (word → level). Words not in the lookup
get `level = <NA>` in the `level` column — kept, not dropped, since they feed
both the fallback-decomposition step below and the "words in exams not in the
official wordlist" comparison feature.

### Fallback: decompose unmatched compound words

A word not being a literal wordlist entry doesn't mean it's unknown vocabulary
— jieba often correctly tokenizes a real, productive combination of two
already-known words (`看电视` = 看 + 电视) that just isn't itself a dictionary
headword. `resolve_level()` recursively tries a set of linguistically-motivated
patterns, each requiring every component to already resolve to a level:

| Pattern | Example |
|---|---|
| Ordinal (+ optional trailing word) | 第一, 第一次 |
| Reduplication (XX) | 看看, 等等 |
| AABB reduplication | 干干净净, 漂漂亮亮 |
| Erhua suffix (儿) | 点儿, 会儿, 事儿 |
| Single char resolved via its doubled form | 妈 (via 妈妈), 爸 (via 爸爸) |
| Pure numeral | 二十八 |
| Numeral + unit (any length) | 半个, 三分钟, 半小时 |
| Function-word prefix (closed class: 不没很太更最也都还就才又挺别这那哪每大小真好先多) | 很多, 不是, 小狗, 先看 |
| Verb + object/complement (closed class: 吃喝看做写坐用洗想走来放带买开变去打) | 吃药, 看电视, 打篮球 |
| Aspect/manner suffix (了/得) | 长得, 改了, 懒得 |
| Pronoun + predicate (我你他她) | 我要, 你好, 我会 |
| Measure word + noun | 本书, 双鞋, 段时间 |
| Two known words concatenated (both ≥2 chars) | 锻炼身体, 今天下午 |

Every pattern is memoized (`functools.lru_cache`) and recursive, so chains
resolve too (`去一趟` = 去 + 一趟, where 一趟 itself only resolves via the
numeral-unit rule).

**This was built incrementally and adversarially** — a naive "all characters
individually known" check was tried first and rejected: it flagged nonsense
adjacent-character noise (`时哭`, `北半球`, `九日山`) just as readily as real
compounds, since almost any two common Chinese characters can combine into
"known pieces" without being a real word. Every pattern above was instead
tested against the *entire* unmatched corpus and manually scanned for false
positives before being kept. Two collisions were caught and fixed this way:

- `大`/`小`/`老` + a single surname character (`小王`, `老张`) is a person's
  name in exam dialogues, not the word modifying that character — blocked
  via a curated surname-character list, but only for single-char tails
  (`小狗`, `老照片` are unaffected).
- `张` was tried as a measure word (张纸/张票) but produced `张老师`/`张律师`
  (titles), since it's also a common surname — excluded from the measure-word
  set entirely.

One thing that was tried and **reverted**: loading CC-CEDICT (~121k words)
into jieba as a supplementary dictionary via `jieba.load_userdict()`, on the
theory that a bigger dictionary could only help segmentation. Measured
result was the opposite — jieba's default dictionary is already frequency-
tuned from a large corpus, and the extra 121k auto-frequency entries shifted
segmentation boundaries that were previously correct into different (not
better) splits, *reducing* the match rate. See notebook section 0d for the
full before/after comparison.

### Cross-check against CC-CEDICT

Words that remain unmatched after decomposition are cross-checked against
[CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) (a
community-maintained Chinese-English dictionary, ~121k curated headwords,
CC BY-SA 4.0, published by MDBG) — downloaded once and cached at
`data/external/cedict_ts.u8` (gitignored, third-party file). Two other
signals were tried first and found weaker:

- `likely_noise` (word seen ≤2 times, in only 1 exam file) — a heuristic, not
  authoritative; real rare words get flagged too.
- `in_jieba_dict` (does jieba's own dictionary contain the word) — jieba's
  dictionary is a statistical corpus dictionary that over-recognizes common
  collocations that aren't real fixed words, so it's a noisier signal than
  a curated dictionary.

`in_cedict` is the strongest of the three — measured via confusion matrix
against the other two (treating `in_cedict` as the ground-truth proxy):
`in_jieba_dict` scores recall 0.962 / precision 0.432 / F1 0.596;
`NOT likely_noise` scores recall 0.554 / precision 0.350 / F1 0.429.

### Results (current run — wordlist snapshot 2026-07-03, 7,410 words)

- 102,315 (word, exam_id, source_type) rows
- **95.5%** of token occurrences matched an HSK level (85.9% direct wordlist
  match + 9.6pp recovered by the decomposition fallback); 61.2% of unique
  words matched
- Remaining unmatched words (~2,943 unique, ~12,500 occurrences) split into:
  words CC-CEDICT confirms are real Chinese (source-wordlist gaps, e.g. `妈`,
  `乒乓球`, `你好` before it was covered), and words neither jieba nor
  CC-CEDICT recognize (near-certainly ASR/OCR noise, e.g. `时哭`, `北半球`)
- The wordlist grew from 5,343 → 7,410 words between runs (mostly HSK5/6
  additions) but the match rate barely moved — this corpus is HSK3/4 exam
  papers only, so HSK5/6 vocabulary additions rarely appear in it. The
  remaining unmatched gap is bounded by out-of-HSK vocabulary in the exams
  (proper nouns, instruction phrases, ASR/OCR noise), not by wordlist size.
- Both categories are **out of scope for this notebook** — see
  `data/processed/unmatched_words_review.csv` and
  `unmatched_words_in_cedict.csv` for follow-up on the wordlist source itself

### Output

- `data/processed/word_counts.parquet` (+ `.csv`) — columns: `word`, `level`
  (direct match only), `exam_id`, `hsk_level`, `source_type`, `count`,
  `match_pattern`, `effective_level` (direct + decomposed), `match_type`
  (`direct`/`decomposed`/`unmatched`)
- `data/processed/unmatched_words_review.csv` — every unmatched word with
  `total_count`, `exam_count`, `char_length`, `all_chars_known`,
  `likely_noise`, `in_jieba_dict`, `in_cedict`
- `data/processed/unmatched_words_in_cedict.csv` — the `in_cedict == True`
  subset, sorted by frequency (highest-confidence source-wordlist candidates)

---

## Diagnostic Plots

Notebook 01 produces a 3-panel matplotlib figure:

1. **Chars extracted vs page count** — scatter per file, colored by HSK level
2. **File size (MB) vs chars/page** — scatter with red dashed threshold line at 150 chars/page (OCR boundary)
3. **Stacked bar by HSK level** — extraction method breakdown (ok / ocr / sparse / cid)

---

## Spot-checking Transcripts

```python
import whisper
model = whisper.load_model("medium")
result = model.transcribe("path/to/file.mp3", language="zh")
print(result["text"][:500])
```

Compare against actual audio. If accuracy is poor on a specific HSK level or accent, try `large` model or Azure Speech Services.

---

## Re-running the Pipeline

All saves use Parquet upsert-style (overwrite). Re-running notebook 01 is safe — it re-inventories, re-extracts, and overwrites the output files. Re-running notebook 02 is safe too — it re-reads `raw_extractions.parquet` fresh and overwrites `word_counts.parquet`. CC-CEDICT is downloaded once to `data/external/cedict_ts.u8` and reused on subsequent runs (delete the file to force a re-download).

The HSK wordlist API cell uses `seen_ids` dedup to stop pagination when all records in a page have already been fetched, preventing infinite loops on APIs that return overlapping pages.

**Wordlist snapshot caching:** the API cell only hits the network if `FORCE_REFRESH = True` or no local snapshot parquet exists yet — otherwise it silently reloads the last saved snapshot, which will look identical run after run even if the source wordlist changed. Set `FORCE_REFRESH = True` once to force a live re-fetch (and set it back to `False` afterward to avoid re-fetching every run). The API's own cache is also webhook-driven from Supabase with a debounce, so a word added at the source can take some time to appear even through a forced re-fetch — check `GET /health` (`cache_records`) against the notebook's fetched total if the count still looks stale.
