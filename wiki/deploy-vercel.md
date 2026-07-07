# Deploying to Vercel + Neon

The deployment target for this project — 100% free tier. Config lives at the
repo root: [`vercel.json`](../vercel.json), [`api/index.py`](../api/index.py),
[`requirements.txt`](../requirements.txt). `infra/main.tf` provisions both the
Neon project and the Vercel project (with this repo linked for auto-deploy)
via Terraform — see [DevSecOps Pipeline](devsecops.md#infrastructure-as-code--terraform)
for the IaC path. This doc covers the manual first-time setup and the
data-loading steps Terraform doesn't handle.

Vercel hosts **both** the React frontend and the FastAPI backend in one
project — the frontend is built as a static site, the API runs as a single
Python serverless function. Same origin, so no CORS configuration is needed
between them (only for any *other* origin that might call the API directly).

> **Why not Mangum?** Mangum adapts an ASGI app to AWS Lambda's `event`/
> `context` payload format. Vercel's Python runtime has native ASGI support —
> a file under `api/` exporting an `app` variable is served directly. Adding
> Mangum here would mean the handler expects a payload shape Vercel never
> sends, and it would fail at runtime. `api/index.py` is just:
> ```python
> from backend.main import app
> ```

---

## 1. Create a Neon project

[Neon](https://neon.tech) is a serverless Postgres provider with a free tier
and a connection-pooling endpoint suited to serverless functions (each
invocation opens/closes a connection rather than holding a long-lived pool).

1. Sign up, create a project and a database (e.g. `hsk_frequency`).
2. Neon gives you **two** connection strings — grab both:
   - **Pooled** (hostname contains `-pooler`) — use this for the running API.
   - **Direct** (no `-pooler`) — use this only for one-off batch scripts
     (loading data), not for the deployed API.
3. Note the host, user, password, and database name out of whichever
   connection string you're using — `backend/db.py` builds the DSN from
   discrete `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`/`DB_SSLMODE` env vars,
   same as the Azure/local setup, not a single `DATABASE_URL`.

## 2. Load data into Neon (one-time, from your machine)

Using Neon's **direct** (non-pooled) connection string — bulk upserts don't
need pgbouncer, and it avoids any pooler statement-caching edge cases:

```bash
export DB_HOST=<direct-host>.neon.tech
export DB_USER=<user>
export DB_PASSWORD=<password>
export DB_NAME=hsk_frequency
export DB_SSLMODE=require

# apply the schema once
psql "postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST/$DB_NAME?sslmode=require" -f db/schema.sql

# load the notebook output
python -m etl.load_word_counts
```

Re-run `load_word_counts` (against the direct endpoint) any time the
notebooks are re-run and you want to refresh the deployed data — this is a
manual step; there's no scheduled/cron job wired up for it.

**After any change to `db/schema.sql`**, also run
[`scripts/check_schema_drift.py`](../scripts/check_schema_drift.py) against
Neon before you consider the deploy done:

```bash
DB_HOST=<host> DB_USER=<user> DB_PASSWORD=<password> DB_NAME=<db> DB_SSLMODE=require \
    python -m scripts.check_schema_drift
```

`CREATE TABLE IF NOT EXISTS` (what `schema.sql` uses throughout) is a no-op
against a table that already exists, so it silently does **not** add a column
that was appended to an existing table's definition — that's exactly what
caused the 2026-07-07 production incident (`definition`/`definition_th` and
`exam_sentences` were added to `schema.sql` and applied locally, but Neon
never got the migration, so `/api/search/word-detail` 500'd on every request).
This script diffs the connected database's actual columns/tables against what
`schema.sql` currently defines and exits non-zero listing anything missing.

## 3. Connect the repo in Vercel

1. In the Vercel dashboard: **New Project** → import this Git repo.
2. Vercel reads [`vercel.json`](../vercel.json) automatically:
   - `buildCommand`: `cd frontend && npm install && npm run build`
   - `outputDirectory`: `frontend/dist` (the static frontend)
   - `rewrites`: sends `/api/*` and `/health` to the one Python function at
     `api/index.py`. FastAPI's own router (already prefixed `/api/frequency`,
     `/api/search`, `/api/compare` in `backend/main.py`) does the final
     dispatch on the full path — no backend route changes were needed for
     this to work.
3. Set the **Project → Settings → Environment Variables** (use Neon's
   **pooled** endpoint here, unlike step 2):

   ```env
   DB_HOST=<pooled-host>.neon.tech
   DB_USER=<user>
   DB_PASSWORD=<password>
   DB_NAME=hsk_frequency
   DB_SSLMODE=require
   CORS_ALLOW_ORIGINS=https://<your-project>.vercel.app
   ```

   (`CORS_ALLOW_ORIGINS` only matters if something *other* than the
   co-hosted frontend calls the API — same-origin requests aren't affected
   by CORS at all.)

4. For the frontend build, also set:

   ```env
   VITE_API_BASE_URL=
   ```

   Leave it **empty** — not `/api`. The frontend's API client already
   prefixes every call with `/api/...` itself (and calls `/health` bare), so
   an empty base URL resolves those as relative to the current origin,
   matching the `vercel.json` rewrites. Setting it to `/api` would double up
   to `/api/api/...` and break every request.

5. Deploy. Every push to the connected branch triggers a new build
   automatically — no custom CI stage needed for this. If you provisioned the
   project via `infra/main.tf` instead of the dashboard, this git connection
   is already set via the `git_repository` block, and steps 1-4 above are
   templated as Terraform resources/variables.

---

## Serverless connection pooling

`backend/db.py` and `etl/load_to_db.py`'s `get_engine()` both switch to
`NullPool` automatically when Vercel's `VERCEL=1` runtime env var is present,
instead of the normal `QueuePool` used for the long-running Docker/Azure/
local process. This matters because a serverless invocation may run in a
fresh, short-lived container — a large pool held open across cold starts can
accumulate stale connections against Neon's pooler rather than help. No
manual toggle needed; Vercel sets `VERCEL=1` for you.

---

## Known gaps

- No scheduled/batch job runs on Vercel for this project — reloading data
  after re-running the notebooks is always the manual step in §2.

## Gotchas hit while getting this working

- **Root `requirements.txt` must be self-contained.** Vercel's Python builder
  (`uv pip install`) doesn't resolve a `-r requirements/api.txt` indirection
  correctly — it ends up trying to build plain `psycopg2` from source (no
  `pg_config` in that sandbox) instead of `psycopg2-binary`. The root
  `requirements.txt` duplicates `requirements/api.txt`'s contents directly;
  keep them in sync manually if you change API dependencies.
- **`psycopg2-binary` needs a version with wheels for Vercel's current Python.**
  Vercel's build ran Python 3.14 at time of writing; `psycopg2-binary==2.9.9`
  has no cp314 wheel, so the build fell back to a source build (same
  `pg_config` failure as above). Pinned to `2.9.12`, which ships cp313/cp314
  wheels — bump again if Vercel moves to an even newer Python and the build
  starts failing the same way.
