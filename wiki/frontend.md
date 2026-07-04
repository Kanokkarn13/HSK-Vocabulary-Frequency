# Frontend Dashboard

Location: [`frontend/`](../frontend). Stack: React 19, Vite, TypeScript, Tailwind CSS v4, Recharts, axios.

---

## Running it

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000
npm install
npm run dev
```

Dev server: `http://localhost:5173`. Requires the API (`backend/main.py`) and a
loaded Postgres database — see [Setup Guide](setup.md) and
[ETL Pipeline](etl-pipeline.md#load_word_countspy) to get data into the DB first.

---

## Structure

```
frontend/src/
├── App.tsx                 # Page layout, filter state (hskLevel, sourceType,
│                            # examLevel, examId), data fetching, stat calculations
├── api/
│   ├── client.ts            # axios instance + fetchTopWords/fetchExams/searchWord
│   └── types.ts              # Response/row types matching the backend schemas
├── components/
│   ├── Navbar.tsx            # Dark masthead header, wordmark, dark-mode toggle
│   ├── FilterBar.tsx         # Word HSK level, source type, exam-paper level, exam picker
│   ├── StatCard.tsx          # Single stat cell (used inside a shared divided strip)
│   ├── TopWordsChart.tsx     # Recharts horizontal bar chart, top 15 words
│   ├── TopWordsTable.tsx     # Full word list — client-side search + pagination
│   ├── SearchPanel.tsx       # Looks up one word via /api/search/word
│   ├── HskBadge.tsx          # Color-coded HSK-level pill
│   ├── StatusPanel.tsx       # Loading / error / empty states shared across sections
│   ├── ErrorBoundary.tsx     # Catches render crashes, shows a full-page fallback
│   └── icons.tsx             # Hand-drawn SVG icon set (no emoji anywhere in the UI)
├── hooks/
│   └── useAsync.ts           # Shared fetch-state hook; sanitizes errors before display
└── index.css                 # Design tokens (see below) + Tailwind v4 dark-mode setup
```

---

## Data flow / filtering model

There are two independent "level" concepts, both exposed as separate filters:

- **Word's HSK level** (`hsk_level` param) — the vocabulary word's own official
  level (1–6), from `hsk_wordlist`.
- **Exam-paper level** (`exam_level` param) — the HSK level *the exam itself*
  was written for (this corpus only has HSK3 and HSK4 papers). Independent of
  the word's own level — an HSK1 word like 你好 appears throughout HSK3 *and*
  HSK4 papers.

Selecting a specific exam (`exam_id`) combines that exam's reading (PDF) and
listening (audio) word counts automatically — the source-type toggle is
disabled and dimmed in this state, with a tooltip explaining why.

`App.tsx` fetches the *entire* matching word list in one call
(`limit` up to 10,000, see [API Endpoints](api-endpoints.md)) rather than
paging server-side — the top-15 chart, the stat cards, and the searchable
table all derive from that single in-memory list. `TopWordsTable` filters out
rows with no matched `hsk_level` (see the project's [scope boundary
note](../README.md) — unmatched words are intentional data, but the *table*
only lists words that resolved to an HSK level. The chart and stat cards are
unaffected by that filter and still reflect the whole scope.

---

## Design tokens (`index.css`)

Tailwind v4's `@theme` block defines two custom color scales instead of using
Tailwind's stock palette directly:

- `--color-brand-*` — the site's accent color. **This has changed a few times
  during development** (muted terracotta → cinnabar red → jade green → the
  current burgundy/wine) specifically to avoid resembling other AI/SaaS
  vendor brand colors (Claude's orange, Supabase's green, etc). If asked to
  change it again, only this scale plus two hardcoded hex fallbacks in
  `TopWordsChart.tsx` (`BAR_COLOR` and the tooltip `itemStyle`) need updating.
- `--color-ink-*` — a warm neutral scale used everywhere instead of Tailwind's
  cool-toned `slate`, for a less generic-SaaS look.

Fonts: `Sarabun` (Thai/Latin body text), `Space Grotesk` (`.font-display`,
headings/numbers), `Noto Serif SC` (`.font-zh`, Chinese word display —
deliberately serif rather than sans, for a more "dictionary" feel).

Dark mode uses a manual `.dark` class toggle. Tailwind v4 defaults to
`prefers-color-scheme`-only dark mode — class-based toggling requires the
`@custom-variant dark (&:where(.dark, .dark *));` line at the top of
`index.css`. Without it, the dark-mode toggle button silently does nothing
(hit this exact bug once during development).

When changing HSK-badge colors (`HskBadge.tsx`) or the brand accent, check
they don't collide — e.g. brand-as-green once matched the HSK-1 badge's
`emerald`, and brand-as-red once matched the HSK-6 badge's `rose`.

---

## Known gaps / non-goals

- `/api/compare/wordlist-vs-actual` exists on the backend but isn't called
  by the frontend — an earlier "words not in HSK" comparison panel was
  removed once the main table gained full-list search (see git history for
  `ComparePanel.tsx`, deleted).
- No routing/pages — this is a single-view dashboard, all filtering happens
  client-side against query params, no react-router.
- No automated frontend tests yet (backend has `tests/test_segment.py`, no
  frontend equivalent).
