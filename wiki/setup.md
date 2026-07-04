# Setup Guide

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | ETL + API |
| Node.js | 20+ | Frontend dashboard (`frontend/`) |
| Docker Desktop | Latest | Run PostgreSQL + API services |
| ffmpeg | Any | Required by Whisper for audio decoding |
| Git | Any | Version control |

ffmpeg on Windows:

```powershell
winget install ffmpeg
# or via choco: choco install ffmpeg
```

---

## Notebook Environment (`C:\ml-env`)

The notebooks require packages that can conflict with each other (PaddleOCR, PyTorch, Whisper). They are installed in a dedicated venv at `C:\ml-env` — the short path avoids Windows MAX_PATH 260-character limit errors during pip install.

### 1. Create the venv

```powershell
python -m venv C:\ml-env
C:\ml-env\Scripts\activate
```

### 2. Install dependencies in order

```powershell
# Base tools first
pip install setuptools wheel

# PaddleOCR — use paddlepaddle 2.6.2 (NOT v3 — oneDNN bug on Windows)
pip install paddlepaddle==2.6.2
pip install paddleocr==2.8.1

# PDF + image processing
pip install pdfplumber pymupdf pillow numpy

# Whisper
pip install openai-whisper --no-build-isolation

# Data + notebook
pip install pandas pyarrow python-dotenv requests ipykernel jupyter
```

> **Why paddlepaddle 2.6.2?** PaddlePaddle v3 has an oneDNN compatibility bug on Windows that causes a crash on import. Stick with 2.6.2 until upstream fixes it.

### 3. Register the Jupyter kernel

```powershell
C:\ml-env\Scripts\python.exe -m ipykernel install --user --name ml-env --display-name "Python (ml-env)"
```

Verify in VS Code: open a `.ipynb` file → click the kernel selector (top right) → select **Python (ml-env)**.

### 4. Configure environment

```powershell
cp .env.example .env
```

Required values in `.env`:

```env
HSK_WORDLIST_API_URL=https://your-flashcard-app.com/api/hsk-words
HSK_WORDLIST_API_KEY=your_api_key_here

WHISPER_MODEL=medium

# Origins allowed to call the API from a browser (comma-separated)
CORS_ALLOW_ORIGINS=http://localhost:5173
```

---

## Project Virtual Environment (`.venv`)

For running the FastAPI backend and ETL scripts (not notebooks):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements/api.txt -r requirements/etl.txt
pip install pytest pytest-cov
```

---

## Full Docker Setup (API + DB)

```bash
docker compose up -d db api
```

The schema in `db/schema.sql` runs automatically on first start via the `docker-entrypoint-initdb.d` mount.

After the notebooks have produced `data/processed/word_counts.parquet` (see
[ETL Pipeline](etl-pipeline.md)), load it into the running database:

```bash
python -m etl.load_word_counts
```

Re-running it is safe — it upserts, so re-run after re-running notebooks 01/02
to refresh the DB with new data.

To run ETL as a one-off container:

```bash
docker compose run etl \
  --source-type listening \
  --input-dir data/listening \
  --whisper-model medium
```

---

## Frontend Setup (`frontend/`)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

`.env` needs one value:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Dev server runs at `http://localhost:5173`. It expects the API to already be
running with data loaded (steps above) — without that, the dashboard shows a
"cannot connect" error banner and empty-state panels rather than crashing.
See [Frontend Dashboard](frontend.md) for the component structure and design
system.

---

## Whisper Model Selection

| Model | Size | VRAM | Speed | Accuracy |
|---|---|---|---|---|
| `tiny` | 39M | ~1GB | Fastest | Lowest |
| `base` | 74M | ~1GB | Fast | Low |
| `small` | 244M | ~2GB | Medium | OK |
| `medium` | 769M | ~5GB | Slow | Good |
| `large` | 1.5GB | ~10GB | Slowest | Best |

Set via `.env`: `WHISPER_MODEL=medium`

The notebook has a `TEST_ONLY = True` flag at the top of the Whisper cell. Set it to `False` before running the full batch.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'paddleocr'` in notebook**  
Wrong kernel selected. Make sure the VS Code kernel is set to **Python (ml-env)**, not `.venv`.

**`ModuleNotFoundError: No module named 'pkg_resources'` during pip install**  
Run `pip install setuptools wheel` first, then retry with `--no-build-isolation`.

**`ModuleNotFoundError: No module named 'dotenv'`**  
Install `python-dotenv` in whichever venv is active: `pip install python-dotenv`.

**PaddleOCR crashes on import (Windows)**  
Check that `paddlepaddle==2.6.2` is installed, not v3. Run `pip show paddlepaddle` to verify.
