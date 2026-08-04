# แผนเก็บงานและ Deploy ให้สมบูรณ์

เอกสารนี้เป็น execution contract สำหรับโมเดลที่รับช่วงทำงานต่อ เป้าหมายคือทำให้โค้ด Full ETL ผ่าน CI, deploy frontend/API และ deploy Airflow แยกจาก Vercel อย่างปลอดภัย

> สถานะ ณ 2026-08-05: **ยังห้าม deploy** จนกว่า Gate A-F ด้านล่างจะผ่านทั้งหมด

## สถานะการดำเนินงานล่าสุด

- Gate A ผ่านใน local branch `codex/airflow-full-etl-deploy` หลัง commit และ rebase บน `origin/master`
- Gate B ผ่าน: แก้ pytest SyntaxError, เพิ่ม no-change gate, retry classification, manifest metrics และ COPY-based staging
- Gate C ผ่าน: isolated full pytest `95 passed`, Airflow image build, compileall, DAG import errors `[]`, forced Full ETL publish/validate และ no-change run
- Gate D ยังรอ GitHub Actions run จริงและ branch protection
- Gate E/F ยังรอ production Airflow host, production secrets, staging backup และ API smoke URL

ดังนั้นสถานะคือ **Full ETL พร้อมสำหรับเปิด PR/CI และ local deployment แล้ว แต่ยังไม่ถือว่า production deploy สมบูรณ์** จนกว่า Gate D-F จะมีหลักฐานครบตาม Definition of Done ด้านล่าง

## 1. กติกาสำหรับโมเดลที่ลงมือทำ

1. อ่านเอกสารนี้ทั้งหมดก่อนแก้ไฟล์
2. ห้ามใช้ `git reset --hard`, `git checkout -- .`, ลบ volume หรือทิ้งไฟล์ที่ผู้ใช้แก้ไว้
3. ห้ามใช้ `git add .` ให้ stage เป็นรายไฟล์เท่านั้น
4. ห้าม commit `.env`, credentials, Terraform state, Airflow logs, raw PDF/audio, Whisper model หรือ private wordlist
5. ห้ามเขียนหรือทดสอบกับ Neon production จนกว่า local/staging gates จะผ่าน
6. ห้ามเปิด scheduler ก่อน Full ETL รุ่นปัจจุบันผ่าน manual 3 รอบ
7. ถ้าต้องใช้ credential, production host หรือการกด merge/deploy ให้หยุดและขอผู้ใช้เฉพาะจุดนั้น
8. หลังแต่ละ phase ให้บันทึกคำสั่งที่รัน ผลลัพธ์ และไฟล์ที่เปลี่ยน
9. ถ้า test ล้ม ต้องแก้ root cause ห้ามใช้ `|| true`, mark success หรือปิด test
10. Vercel/API และ Airflow เป็นคนละ deployment ห้ามรายงานว่า Airflow deploy แล้วเพียงเพราะ Vercel deploy สำเร็จ

## 2. สถาปัตยกรรมเป้าหมาย

```text
GitHub PR
   ├── CI: API/ETL tests + security + Terraform validation
   ├── CI: Airflow image build + DAG import + Compose checks
   └── Vercel Preview
              ↓ merge เมื่อทุก check ผ่าน
Vercel Production
   ├── React frontend
   └── FastAPI serverless API ─── Neon pooled endpoint

Airflow Production (runtime แยก)
   ├── scheduler / DAG processor / API server / triggerer
   ├── persistent metadata PostgreSQL
   ├── persistent source/staging/model-cache storage
   └── HSK ETL database writes ─── Neon direct endpoint
```

Vercel ไม่สามารถรัน Airflow scheduler หรือ Whisper job ที่ทำงานยาวได้ จึงต้องมี Airflow runtime แยกต่างหาก

### Runtime ที่ต้องเลือกก่อน Phase E

ตัวเลือกที่แนะนำสำหรับโปรเจกต์ส่วนตัวคือ Linux VM หรือ self-hosted Docker host แบบ private มี persistent disk และ backup หากต้องการ production ที่ดูแลง่ายกว่า ให้ใช้ managed Airflow หรือ Kubernetes + official Helm chart

Airflow ระบุว่า Docker Compose quick-start ไม่มี security guarantees สำหรับ production และแนะนำ official Helm chart เมื่อพร้อมใช้ production: <https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/>

ถ้ายังไม่มี runtime ให้ทำได้ถึง Gate D เท่านั้น แล้วรายงานว่า “application พร้อม แต่ Airflow production ยังไม่มี host” ห้ามอ้างว่า deploy สมบูรณ์

## 3. ปัญหาที่พบแล้วและต้องแก้

- [ ] `tests/test_manifest_transform.py` บรรทัดประมาณ 83 มี f-string ปีกกาไม่สมดุล ทำให้ `pytest` หยุดด้วย `SyntaxError`
- [ ] Full ETL/Airflow files ส่วนใหญ่ยัง untracked หรือ uncommitted
- [ ] branch ปัจจุบัน `fix/flaky-test-assertions` ถูก merge แล้วและตามหลัง `origin/master` 14 commits
- [ ] local worktree มีประมาณ 44 รายการ ห้ามรวม local config/generated data เข้า commit โดยไม่ตรวจ
- [ ] GitHub CI ล่าสุดบน `master` ยังเป็นโค้ดเก่าและไม่มี Airflow job รุ่นนี้
- [ ] Airflow CI ใน local workflow เรียก Compose แต่ไม่ได้สร้าง `.env`; GitHub runner จะไม่มีไฟล์นี้
- [ ] Airflow CI ยังไม่ build image และไม่ assert ว่า DAG import errors เป็นศูนย์
- [ ] มี Full ETL success จริงเพียง 1 รอบ; successful runs อีก 2 รอบเป็น load-only DAG รุ่นเก่า
- [ ] no-change run ยังไม่มี short-circuit ที่หยุด Transform/DB publish
- [ ] schedule, require-source และ require-API ยังเป็น `false`
- [ ] API smoke-test URL และ alert webhook ยังไม่ตั้ง
- [ ] Compose ปัจจุบันเป็น local development: `host.docker.internal`, Simple Auth และ development secret fallbacks
- [ ] `master` ไม่มี branch protection และ Vercel auto-deploy เมื่อ push เข้า master
- [ ] Terraform CLI ไม่มีในเครื่อง จึงต้องยืนยันด้วย CI หรือ runner ที่ติดตั้ง Terraform

## 4. Phase A — รักษางานเดิมและจัด Git ให้สะอาด

### A1. ตรวจและสร้าง branch ใหม่

รัน:

```powershell
git status --short
git branch --show-current
git rev-list --left-right --count HEAD...origin/master
git switch -c codex/airflow-full-etl-deploy
git fetch origin
```

หาก branch นี้มีอยู่แล้ว ให้ใช้ชื่อ `codex/airflow-full-etl-deploy-2` ห้ามเขียนทับ branch เดิม

### A2. แบ่งไฟล์

กลุ่มที่ควรอยู่ใน Full ETL commit:

- `airflow/**` ยกเว้น logs/generated config/password file
- `etl/extract_wordlist.py`
- `etl/manifest.py`
- `etl/transform_batch.py`
- `etl/stage_database.py`
- `etl/tokenizer.py`
- `etl/hsk_components.py`
- การเปลี่ยนใน `etl/load_to_db.py`, `etl/load_word_counts.py`, `etl/pipeline.py`, `etl/segment_and_count.py` ที่เกี่ยวกับ data contract ใหม่
- tests ที่เกี่ยวข้อง
- `.github/workflows/ci-cd.yml`
- `.gitignore`
- เอกสารใน `wiki/` ที่เกี่ยวข้อง
- notebook/scripts benchmark เฉพาะส่วนที่ reproducible และใช้ config เดียวกับ production

กลุ่มที่ห้าม stage อัตโนมัติ:

- `.env`, `.claude/**`, `.vscode/settings.json`, `pyrightconfig.json` ถ้าเป็น local-only
- `airflow/logs/`, `airflow/config/airflow.cfg`, password file
- `data/reading/`, `data/listening/`, `data/raw/`, `data/staging/`
- private HSK wordlist snapshot
- generated Parquet/CSV เว้นแต่ผู้ใช้ยืนยันว่าเป็น portfolio artifact ที่ต้อง version

ให้ตรวจ diff ทุกไฟล์ก่อนตัดสินใจ:

```powershell
git diff -- <file>
git diff --check
```

### A3. Commit ก่อน sync

ใช้ explicit paths เท่านั้น ตัวอย่าง:

```powershell
git add airflow etl tests wiki/deploy-completion-execution-plan.md wiki/airflow-full-etl-improvement-plan.md .github/workflows/ci-cd.yml .gitignore
git diff --cached --stat
git diff --cached --check
git commit -m "Implement production-gated Airflow full ETL"
git rebase origin/master
```

หาก rebase conflict ให้แก้ทีละไฟล์และรันทดสอบใหม่ ห้ามใช้ ours/theirs ทั้ง repository

### Gate A

- [ ] branch ใหม่สร้างจากงานเดิมโดยไม่มีข้อมูลหาย
- [ ] ไม่มี secret/generated/private source ใน staged files
- [ ] branch rebase บน `origin/master` ล่าสุดสำเร็จ
- [ ] `git status` ไม่มีไฟล์ที่ตั้งใจ deploy ค้างแบบ untracked

## 5. Phase B — แก้ correctness และ incremental behavior

### B1. แก้ SyntaxError ใน test

ห้ามสร้าง JSON ด้วย f-string ที่ต้อง escape `{}` ให้ใช้ `json.dumps()`:

```python
manifest.write_text(
    json.dumps({
        "sources": [{
            "source_key": "reading:x.pdf",
            "exam_id": "x",
            "hsk_level": 3,
            "source_type": "reading",
            "filename": "x.pdf",
            "text_path": text_path.as_posix(),
        }]
    }, ensure_ascii=False),
    encoding="utf-8",
)
```

### B2. เพิ่ม no-change short-circuit

เพิ่ม state ที่ชัดเจนจาก Extract:

- wordlist: `changed: bool`
- PDF/audio: `changed_source_count`, `reused_source_count`
- inventory: current checksum summary

เพิ่ม task `should_process_batch` หลัง PDF/audio extract และก่อน `build_raw_snapshot`/Transform

เงื่อนไขให้รันต่อเมื่ออย่างน้อยหนึ่งข้อเป็นจริง:

1. wordlist changed
2. PDF/audio อย่างน้อยหนึ่งไฟล์ changed
3. ยังไม่มี `etl_publish_state` ของ production
4. `HSK_FORCE_FULL_RUN=true`

ถ้าไม่มีการเปลี่ยนแปลง ให้ downstream เป็น skipped และ DAG Run จบ success โดยไม่ stage/publish database

ใช้ Airflow short-circuit/branch ที่รองรับใน Airflow 3.3.0 และเพิ่ม regression test ตรวจ task behavior

### B3. Retry แยก transient/permanent error

กำหนดต่อ task:

| Task | Retries |
|---|---:|
| wordlist API | 3 สำหรับ timeout/429/5xx |
| 401/403/schema/quality error | 0 โดย raise non-retryable Airflow exception |
| inventory | 1 |
| PDF extraction | 0 |
| Whisper | 1 พร้อม checkpoint |
| transform/quality gate | 0 |
| DB staging | 2 |
| publish | 1 |
| validation | 0 |
| smoke test | 1 |

ห้ามใช้ default retry เดียวกับทุก task เพราะ logic/schema error จะได้ผลเดิมเมื่อ retry

### B4. Timezone ให้ตรงเวลาไทย

ปัจจุบัน cron `0 2 * * 1` กับ naive `start_date` ถูกตีความตาม default timezone ซึ่งมักเป็น UTC หากต้องการวันจันทร์ 02:00 เวลาไทย ให้ใช้ timezone-aware start date เช่น:

```python
import pendulum

start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok")
```

Airflow เก็บเวลาใน UTC แต่ schedule ของ timezone-aware DAG จะใช้ timezone ของ DAG: <https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/timezone.html>

### B5. เพิ่ม production flags

ต้องมีอย่างน้อย:

```env
HSK_FORCE_FULL_RUN=false
HSK_PUBLISH_ENABLED=false
HSK_AIRFLOW_ENABLE_SCHEDULE=false
HSK_REQUIRE_SOURCE_FILES=true
HSK_WORDLIST_REQUIRE_API=true
```

`HSK_PUBLISH_ENABLED=false` ต้องทำให้ run ได้ถึง staging validation แล้ว skip ก่อน production publish เพื่อใช้ทดสอบ staging environment

### B6. Tests ที่ต้องเพิ่ม

- no-change ทำให้ transform/stage/publish ไม่ถูกรัน
- force full run ข้าม no-change gate ได้
- first run ไม่มี publish state ต้องรันต่อ
- 401/403 ไม่ถูก retry
- 429/5xx/timeout ใช้ retry
- corrupt PDF/audio quarantine และ production batch ไม่เปลี่ยน
- publish exception ทำให้ transaction rollback และ `etl_publish_state` ยังเป็น batch เดิม
- duplicate/empty raw rows fail ก่อน publish
- match rate ต่ำหรือ HSK1 สูงเกิน fail ก่อน DB

### Gate B

- [ ] Python compile ผ่านทุกไฟล์รวม tests
- [ ] no-change short-circuit ทำงานจริง
- [ ] retry ตรงชนิด error
- [ ] timezone ตรง Asia/Bangkok
- [ ] publish สามารถปิดสำหรับ dry run
- [ ] rollback tests ผ่าน

## 6. Phase C — Tests และ local acceptance

### C1. Static checks

```powershell
git diff --check
docker compose -f airflow/config/docker-compose.airflow.yml config --quiet
docker compose -f airflow/config/docker-compose.airflow.yml build --no-cache airflow-scheduler
docker compose -f airflow/config/docker-compose.airflow.yml up -d
docker compose -f airflow/config/docker-compose.airflow.yml exec airflow-scheduler python -m compileall -q etl airflow/dags tests
docker compose -f airflow/config/docker-compose.airflow.yml exec airflow-scheduler airflow dags list-import-errors -o json
```

ผล import errors ต้องเป็นรายการว่างจริง ห้ามดูเฉพาะ exit code

### C2. Unit/full tests

ติดตั้ง test dependencies ใน test environment ไม่ใช่ production image แล้วรัน:

```powershell
pytest tests/ -v
npm.cmd run build
npm.cmd run lint
```

DB-backed tests ต้องใช้ PostgreSQL test instance แยก ห้ามใช้ Neon production

Lint warnings ปัจจุบันที่ควรเก็บเป็น backlog แต่ไม่จำเป็นต้อง block release:

- `HskBadge.tsx`: fast-refresh warning
- `useAsync.ts`: exhaustive-deps warning
- frontend bundle ประมาณ 626 KB ควร code split ภายหลัง

### C3. Manual Full ETL 3 รอบ

ให้ schedule ปิดตลอดการทดสอบ

1. รอบแรก: `HSK_FORCE_FULL_RUN=true`, publish เข้า local test DB
2. รอบสอง: ไม่เปลี่ยน input ต้องจบ success โดย Transform/DB เป็น skipped
3. รอบสาม: เพิ่มหรือแก้ source test หนึ่งไฟล์ ต้อง extract เฉพาะไฟล์นั้นและ publish batch ใหม่

ทดสอบ failure เพิ่มต่างหาก:

- API timeout/401/bad schema
- corrupt PDF
- audio transcription failure
- transform quality fail
- DB staging fail
- publish transaction fail

ทุก failure ก่อน publish ต้องไม่เปลี่ยน production counts หรือ publish-state

### Gate C

- [ ] unit/full tests ผ่านทั้งหมด
- [ ] frontend build ผ่าน
- [ ] Airflow image clean build ผ่าน
- [ ] DAG import errors เป็นศูนย์
- [ ] Full ETL รุ่นปัจจุบันผ่าน 3 รอบตามรูปแบบด้านบน
- [ ] failure matrix ยืนยัน last successful batch

## 7. Phase D — แก้ CI และ GitHub release gate

### D1. แก้ Airflow CI

ก่อน Compose command ให้สร้าง `.env` สำหรับ CI จากตัวอย่าง:

```yaml
- name: Prepare CI environment
  run: cp .env.example .env
```

Airflow job ต้องทำอย่างน้อย:

1. Compose config
2. build Airflow image
3. start metadata DB/init/scheduler/DAG processor/API server/triggerer
4. assert DAG import errors เท่ากับศูนย์
5. assert pools ครบ
6. run ETL regression tests
7. stop test containers ใน `if: always()`; ลบได้เฉพาะ CI volumes ที่ job สร้างเอง

ตัวอย่างลำดับ dependency:

```yaml
test: ...
airflow:
  needs: test
security:
  needs: [test, airflow]
terraform:
  needs: [security, airflow]
```

ห้ามให้ Airflow job เป็นเพียง `py_compile` เพราะจะไม่พบ dependency/import/runtime errors

### D2. Branch protection

ตั้ง `master` ให้:

- merge ผ่าน pull request เท่านั้น
- require branches to be up to date
- require checks: Test, Airflow DAG & Compose Check, Security & Quality Scan, IaC Syntax Check
- ห้าม direct push เพื่อ production deploy

Vercel auto-deploy หลัง merge ได้ เพราะ PR commit ผ่าน checks แล้ว แต่ต้องยืนยัน preview ก่อน merge

### D3. PR

ก่อน push:

```powershell
git status --short
git diff origin/master...HEAD --stat
git diff origin/master...HEAD --check
```

จากนั้น push branch และเปิด Draft PR ก่อน ตรวจ diff และ CI แล้วค่อยเปลี่ยนเป็น Ready

### Gate D

- [ ] CI ทุก job ผ่านบน commit เดียวกับ PR head
- [ ] Airflow job build/run จริง
- [ ] Vercel preview ผ่าน health/API smoke tests
- [ ] branch protection เปิดแล้ว
- [ ] ไม่มี secret scan finding
- [ ] PR diff ไม่มี local/generated files

## 8. Phase E — เตรียม Airflow production runtime

Phase นี้ต้องมี runtime target และ credential จากผู้ใช้ก่อน

### E1. ห้ามใช้ development Compose ตรง ๆ

สร้าง production-specific image/manifest:

- image ต้อง `COPY` DAG และ `etl/` เข้า immutable image ไม่ bind mount repository ทั้งก้อน
- pin Airflow/Python/dependencies เหมือน local image
- persistent volume สำหรับ Airflow metadata, logs, source data, staging และ Whisper model cache
- `restart: unless-stopped` หรือ deployment restart policy ที่เทียบเท่า
- healthchecks สำหรับ API server/scheduler/metadata DB
- resource limits; Whisper ต้องมี RAM/CPU เพียงพอ
- ไม่ expose Airflow UI สู่ public internet โดยตรง ให้ใช้ private network/VPN หรือ TLS reverse proxy

### E2. Authentication และ secrets

Simple Auth มีไว้สำหรับ development/testing; หากใช้ production ต้องมี external access control ตามเอกสาร Airflow: <https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/auth-manager/simple/>

สำหรับ production ให้เลือก FAB/SSO auth manager หรือจำกัด UI หลัง VPN/private network ห้ามใช้ default password

ต้องสร้างค่าจริงใหม่:

- `AIRFLOW__API__SECRET_KEY`
- `AIRFLOW__API_AUTH__JWT_SECRET`
- `AIRFLOW__CORE__FERNET_KEY`
- Airflow metadata DB password
- Neon direct DB credential สำหรับ ETL
- HSK wordlist API key
- alert webhook credential

ห้ามมี fallback เช่น `changeme` หรือ `local-dev-secret` ใน production manifest ใช้ required-variable syntax หรือ secrets backend

Airflow รองรับ secrets backend และ environment-based connections: <https://airflow.apache.org/docs/apache-airflow/stable/security/secrets/secrets-backend/> และ <https://airflow.apache.org/docs/apache-airflow/stable/howto/connection.html>

### E3. Database endpoints

- Vercel API ใช้ Neon **pooled endpoint**
- Airflow bulk load ใช้ Neon **direct endpoint**
- ตั้ง `DB_SSLMODE=require`
- production ห้ามใช้ `host.docker.internal`
- Airflow metadata DB ต้องแยกจาก application DB

### E4. Durable data

source PDF/audio ไม่อยู่ใน Git ต้องมี mounted durable storage ที่ path ซึ่ง DAG ใช้

ต้องเก็บถาวร:

- source PDF/audio
- extraction manifest/checkpoints
- raw and processed snapshots
- staging artifacts ตาม retention policy
- quarantine
- Whisper model cache

### E5. Monitoring

ต้องตั้ง:

- `HSK_ALERT_WEBHOOK_URL`
- `HSK_API_SMOKE_URL=https://hsk-vocabulary-frequency.vercel.app/health` หรือ endpoint ที่ตรวจข้อมูล batch ใหม่จริง
- log retention
- disk/CPU/RAM monitoring
- notification เมื่อ task failed/retried และเมื่อ scheduler ไม่ heartbeat

### Gate E

- [ ] Airflow runtime target ถูกระบุและเข้าถึงได้
- [ ] production image immutable
- [ ] secrets ไม่มี default/placeholder
- [ ] UI ไม่เปิด public โดยไม่มี access control
- [ ] persistent storage/backup พร้อม
- [ ] Neon direct connection + SSL ผ่าน
- [ ] alerts และ health monitoring ส่งได้จริง

## 9. Phase F — Staging, database และ production deploy

### F1. Database backup/schema

ก่อน publish ข้อมูลจริง:

1. สร้าง Neon branch หรือ staging database
2. apply `db/schema.sql`
3. รัน `scripts/check_schema_drift.py`
4. รัน Airflow โดย `HSK_PUBLISH_ENABLED=false` ให้ผ่าน staging validation
5. เปิด publish เฉพาะ staging DB และทำ failure/rollback tests
6. ก่อน production publish ให้สร้าง backup/Neon restore point หรือ `pg_dump`

### F2. Deploy application

1. PR checks และ Vercel Preview ผ่าน
2. merge เข้า protected `master`
3. รอ Vercel production deployment success
4. ตรวจ:

```text
GET /
GET /health
GET /api/frequency/top?limit=1
GET /api/search/word?q=你&limit=1
```

ทุก endpoint ต้องได้ 200 และ response schema ถูกต้อง

### F3. Deploy Airflow โดย schedule ยังปิด

1. deploy image ด้วย immutable tag เช่น Git SHA
2. migrate Airflow metadata DB
3. สร้าง/ตรวจ pools
4. ตรวจ DAG import errors
5. manual trigger หนึ่งรอบกับ production inputs
6. ตรวจ database counts, publish state และ application API
7. ถ้าทุกอย่างผ่าน จึงตั้ง `HSK_AIRFLOW_ENABLE_SCHEDULE=true`
8. ยืนยัน schedule วันจันทร์ 02:00 Asia/Bangkok ในหน้า DAG details

### F4. Rollback

หาก application fail:

- rollback Vercel ไป previous deployment
- ตรวจ API health และ DB schema compatibility

หาก Airflow fail:

- ปิด schedule ก่อน
- ห้าม clear production data
- deploy image tag ก่อนหน้า
- ใช้ last successful batch/transaction rollback
- restore database จาก backup เฉพาะเมื่อ transaction rollback ไม่เพียงพอและผู้ใช้อนุมัติ

### Gate F — Definition of Done

- [ ] clean Git branch/PR และ checks ผ่านทุก job
- [ ] current Full ETL tests ผ่านทั้งหมด
- [ ] Full ETL manual 3 รอบผ่าน
- [ ] no-change run ไม่ transform/publish ซ้ำ
- [ ] corrupt source/API/quality/DB failures ไม่เปลี่ยน production
- [ ] Vercel production และ API smoke tests ผ่าน
- [ ] Neon schema drift เป็นศูนย์และมี backup
- [ ] Airflow production มี persistent storage, secure auth, secrets และ monitoring
- [ ] Airflow manual production run ผ่าน
- [ ] weekly schedule เปิดหลัง acceptance เท่านั้น
- [ ] มี Git SHA, image tag, deployment URL, batch ID และ rollback reference ใน release report

## 10. รูปแบบรายงานที่โมเดลต้องส่งกลับ

```markdown
## Deployment completion report

- Git branch / commit:
- PR URL:
- CI run URL and jobs:
- Vercel preview URL:
- Vercel production URL:
- Airflow image tag:
- Airflow runtime target:
- Full ETL successful run IDs (3):
- Production manual run ID:
- Published batch ID:
- DB backup/restore reference:
- Health/API smoke results:
- Schedule state and next run:
- Remaining warnings:
- Rollback command/reference:
```

ห้ามใช้คำว่า “deploy สมบูรณ์” หากช่องบังคับใดว่าง หรือ Gate A-F ยังไม่ครบ
