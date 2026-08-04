# แผนปรับปรุง Airflow ให้เป็น Full ETL แบบปลอดภัย

เอกสารนี้ต่อยอดจาก DAG ปัจจุบัน `hsk_batch_pipeline` ซึ่งย้ายเฉพาะขั้น Load เข้า Airflow สำเร็จแล้ว เป้าหมายถัดไปคือย้าย Extract และ Transform เข้ามาด้วย โดยต้องรันซ้ำได้ ตรวจสอบย้อนหลังได้ และไม่ทำให้ข้อมูลชุดที่ใช้งานอยู่เสียเมื่อ task ใด task หนึ่งล้ม

## 1. สถานะปัจจุบัน

DAG ปัจจุบันทำงานดังนี้:

```text
check_input_files
        ↓
load_word_counts
        ↓
load_sentences
        ↓
validate_database
```

ข้อดีคือ Airflow, Docker, metadata database และการเชื่อมต่อฐานข้อมูลแอปทำงานครบแล้ว แต่ DAG ยังอ่าน artifact ที่ Notebook สร้างไว้ก่อนหน้า จึงยังไม่ใช่ Full ETL

สิ่งที่ยังอยู่นอก Airflow:

| แหล่งข้อมูล | ขั้นตอนปัจจุบัน | การเปลี่ยนแปลงที่ต้องตรวจ |
|---|---|---|
| HSK wordlist API | Notebook 01 | เพิ่มคำ แก้ระดับ แก้ pinyin/คำแปล |
| PDF ข้อสอบ | Notebook 01 / `etl.extract_pdf` | มีไฟล์ใหม่หรือไฟล์เดิมถูกแก้ |
| Audio ข้อสอบ | Notebook 01 / Whisper | มีไฟล์ใหม่หรือไฟล์เดิมถูกแก้ |
| CC-CEDICT | Notebook 02 | เวอร์ชัน dictionary เปลี่ยน |
| การตัดคำ HSK | Notebook 02 / `etl.tokenizer` | config หรือโค้ด tokenizer เปลี่ยน |

## 2. เป้าหมายของ Full ETL

เมื่อ Airflow เริ่มหนึ่งรอบ ระบบต้องทำตามลำดับนี้:

```text
start
  ↓
inventory_sources
  ├── refresh_wordlist_if_changed
  ├── extract_changed_pdfs
  └── transcribe_changed_audio
              ↓
       build_raw_snapshot
              ↓
     validate_raw_snapshot
              ↓
   segment_and_count_for_hsk
              ↓
      validate_transform
              ↓
       stage_database_load
              ↓
       validate_staging_db
              ↓
          publish_batch
              ↓
        validate_production
```

หลักสำคัญคือทุก task เขียนลงพื้นที่ staging ของรอบนั้นก่อน ห้ามเขียนทับ artifact หรือฐานข้อมูล production ระหว่างที่ pipeline ยังตรวจไม่ครบ

## 3. เวลาและเงื่อนไขการ Extract

### ระยะพัฒนา

ใช้ `schedule=None` และ trigger ด้วยมือจนกว่า Full ETL จะผ่านอย่างน้อย 3 รอบติดกัน รวมทั้งทดสอบ failure case แล้ว

### ระยะใช้งานปกติ

แนะนำให้รันสัปดาห์ละครั้ง เช่น วันจันทร์ 02:00 เวลาไทย เพราะข้อมูลข้อสอบและ wordlist ไม่ได้เปลี่ยนทุกวัน:

```python
schedule="0 2 * * 1"
catchup=False
max_active_runs=1
```

หนึ่งรอบของ DAG จะ “ตรวจ” ทุกแหล่งข้อมูล แต่ไม่จำเป็นต้องประมวลผลทุกอย่างใหม่:

- Wordlist API: ขอ metadata หรือดึงข้อมูลแล้วคำนวณ checksum ถ้าเหมือน snapshot ล่าสุดให้ skip
- PDF: เปรียบเทียบ path, file size และ SHA-256 กับ manifest ล่าสุด แล้ว extract เฉพาะไฟล์ใหม่หรือไฟล์ที่เปลี่ยน
- Audio: ใช้วิธีเดียวกับ PDF และเรียก Whisper เฉพาะไฟล์ที่เปลี่ยน
- Transform: รันเมื่อ raw snapshot, wordlist snapshot, dictionary version หรือ tokenizer version เปลี่ยน
- Load: รันเมื่อ transform สร้าง batch ใหม่ที่ผ่าน quality check แล้วเท่านั้น

ไม่ใช้เวลาแก้ไขไฟล์เพียงอย่างเดียวเป็นตัวตัดสิน เพราะเวลาไฟล์อาจเปลี่ยนจากการ copy โดยที่เนื้อหาเดิม ให้ SHA-256 เป็นตัวตัดสินหลัก

## 4. โครงสร้างข้อมูลต่อหนึ่งรอบ

แต่ละ DAG run ควรมี `batch_id` เช่น logical date หรือ run ID ที่แปลงเป็นชื่อโฟลเดอร์ปลอดภัย:

```text
data/
├── source/                    # PDF และ audio ต้นฉบับ
├── staging/
│   └── <batch_id>/
│       ├── manifest.json
│       ├── hsk_wordlist.parquet
│       ├── raw_extractions.parquet
│       ├── hsk_component_counts.parquet
│       └── quality_report.json
└── current/                   # ชี้ไปยัง batch ล่าสุดที่ publish สำเร็จ
```

ข้อกำหนด:

- task ส่งผ่าน XCom เฉพาะข้อมูลขนาดเล็ก เช่น `batch_id`, path, checksum และจำนวน row
- DataFrame, transcript และ Parquet ต้องเก็บใน storage ไม่ส่งผ่าน XCom
- manifest ต้องบันทึก source checksum, config version, tokenizer version, row count และเวลาที่สร้าง
- ถ้า retry task เดิม ต้องเขียนผลเดิมลง staging ของ `batch_id` เดิมได้อย่างปลอดภัย

## 5. กติกาเมื่อ task ล้ม

ใช้ trigger rule ปกติ `all_success` สำหรับเส้นทางหลัก เพื่อให้ downstream หยุดทันทีเมื่อ upstream ไม่ผ่าน

| Task | ตัวอย่างสาเหตุ | Retry | ผลเมื่อยังไม่ผ่าน |
|---|---|---:|---|
| `inventory_sources` | mount หาย, อ่านโฟลเดอร์ไม่ได้ | 1 | หยุดทั้ง DAG และไม่เปลี่ยน production |
| `refresh_wordlist_if_changed` | timeout, HTTP 429/5xx | 3 แบบ exponential backoff | ใช้ snapshot เดิมได้เฉพาะเมื่อกำหนด freshness policy ผ่าน มิฉะนั้นหยุด DAG |
| `refresh_wordlist_if_changed` | API key ผิด, HTTP 401/403 | 0 | fail ทันที เพราะ retry ไม่ช่วย |
| `extract_changed_pdfs` | PDF เสียหรืออ่านไม่ได้ | 0 สำหรับไฟล์นั้น | quarantine ไฟล์และ fail quality gate ห้าม publish แบบเงียบ ๆ |
| `transcribe_changed_audio` | worker/OOM/ปัญหาชั่วคราว | 1 | resume จาก checkpoint รายไฟล์ ไม่เริ่มไฟล์ที่สำเร็จแล้วใหม่ทั้งหมด |
| `validate_raw_snapshot` | key ซ้ำ, text ว่าง, จำนวนไฟล์ลดผิดปกติ | 0 | fail ทันทีและเก็บ staging ไว้ตรวจ |
| `segment_and_count_for_hsk` | bug/config ผิด | 0 | fail ทันที เพราะการรันซ้ำด้วยโค้ดเดิมจะได้ผลเดิม |
| `stage_database_load` | connection หลุด/deadlock | 2 | rollback transaction ของ staging load |
| `validate_staging_db` | row count หรือ distribution ผิด | 0 | ห้าม publish และ production ยังเป็น batch เดิม |
| `publish_batch` | transaction fail | 1 | rollback ทั้ง transaction ต้องไม่เห็นข้อมูลครึ่ง batch |
| `validate_production` | count หลัง publish ไม่ตรง | 0 | แจ้งเตือนระดับสูงและใช้ rollback procedure |

ความหมายของสถานะ:

- `up_for_retry`: task มีปัญหาชั่วคราวและ Airflow จะลองใหม่ตาม policy
- `failed`: task ใช้ retry หมดหรือเป็น error ที่ไม่ควร retry
- `upstream_failed`: task ไม่ถูกรัน เพราะ task ก่อนหน้าล้ม
- `skipped`: task ตรวจแล้วว่าไม่มีข้อมูลเปลี่ยน จึงข้ามโดยตั้งใจ ไม่ถือเป็นความล้มเหลว

## 6. การป้องกันข้อมูลครึ่งชุด

### Artifact

ห้ามเขียนทับ `data/current` โดยตรง ให้เขียน `data/staging/<batch_id>` แล้วตรวจให้ครบ เมื่อผ่านจึงเปลี่ยน pointer หรือ rename ไปเป็น current แบบ atomic

### Database

ระยะที่เหมาะกับโปรเจกต์นี้มี 2 ทางเลือก:

1. เพิ่ม `batch_id` ให้ตาราง staging แล้ว publish ด้วย transaction เดียว
2. โหลดลง staging tables เช่น `word_frequencies_staging` และ `exam_sentences_staging` แล้วตรวจ ก่อน swap/replace ใน transaction เดียว

แนะนำทางเลือกที่ 2 ก่อน เพราะเข้าใจง่ายและแยกข้อมูลที่กำลังสร้างออกจาก production ชัดเจน

`load_word_counts` และ `load_sentences` ไม่ควร publish คนละช่วงอีกต่อไป เพราะถ้าตัวแรกสำเร็จแต่ตัวหลังล้ม ผู้ใช้จะเห็น word counts รุ่นใหม่กับ sentences รุ่นเก่า

## 7. Data quality gates

ทุก threshold ต้องเก็บใน config และปรับจาก baseline ไม่ฝังตัวเลขกระจายใน DAG

### หลัง Extract

- `(exam_id, source_type)` ต้องไม่ซ้ำ
- source file ที่อยู่ใน manifest ต้องมี extraction result ครบ
- text ต้องไม่ว่าง และสัดส่วนตัวอักษรจีนต้องไม่ลดผิดปกติ
- จำนวนข้อสอบห้ามลดจาก last successful batch โดยไม่มีรายการไฟล์ที่ถูกถอนอย่างตั้งใจ
- wordlist ต้องมี `word`, `level` และจำนวนคำต้องไม่ลดฮวบ เช่นเกิน 5% จาก batch ล่าสุด

### หลัง Transform

- `(word, exam_id, source_type)` ต้องไม่ซ้ำ
- count ต้องเป็นจำนวนเต็มและไม่ติดลบ
- HSK match rate ไม่ควรต่ำกว่า baseline เกิน 2 percentage points
- สัดส่วนคำที่ตก HSK 1 ต้องไม่เปลี่ยนจาก baseline เกินค่าที่กำหนด เช่น 5 percentage points โดยไม่มีการอนุมัติ
- รัน regression cases ของ tokenizer ที่อยู่ใน `data/validation` ทุกครั้งที่ tokenizer/config เปลี่ยน
- บันทึก Jieba/HSK tokenizer config และ dictionary checksum ลง manifest

### หลัง Load

- จำนวนแถว staging ต้องตรงกับ artifact
- foreign/reference keys ของ exam ต้องมีครบ
- aggregate ที่คำนวณจาก frequency ต้องตรงกับ query ตรวจตัวอย่าง
- API smoke test ต้องอ่าน batch ใหม่ได้ก่อนประกาศว่ารอบสำเร็จ

## 8. การควบคุม Scheduler และทรัพยากร

ตั้งค่าระดับ DAG:

```python
catchup=False
max_active_runs=1
max_active_tasks=3
dagrun_timeout=timedelta(hours=8)
```

สร้าง Airflow pools:

| Pool | Slots | Task |
|---|---:|---|
| `hsk_api_pool` | 1 | wordlist API |
| `hsk_whisper_pool` | 1 | transcribe audio |
| `hsk_db_write_pool` | 1 | stage/publish database |

เหตุผล:

- `max_active_runs=1` ป้องกันสอง batch เขียน staging/database พร้อมกัน
- Whisper จำกัดหนึ่งงานเพื่อไม่ให้ RAM/CPU เต็ม
- database writer จำกัดหนึ่งงานเพื่อป้องกัน lock และการ publish ชนกัน
- PDF และ API สามารถทำขนานกับ audio ได้เมื่อไม่ใช้ resource เดียวกัน

ไม่ใช้ `depends_on_past=True` เป็นค่าเริ่มต้น เพราะ failure ของสัปดาห์ก่อนจะทำให้รอบใหม่ติดค้างโดยไม่จำเป็น การป้องกันข้อมูลซ้ำให้ใช้ idempotency, manifest และ `max_active_runs=1`

## 9. Timeout และ retry ที่แนะนำ

| Task group | `execution_timeout` | Retries |
|---|---:|---:|
| inventory/checksum | 15 นาที | 1 |
| wordlist API | 10 นาที | 3, exponential backoff |
| PDF extraction | 90 นาที | 0-1 |
| Whisper | 6 ชั่วโมง | 1 และ checkpoint รายไฟล์ |
| Transform | 2 ชั่วโมง | 0 |
| DB staging load | 45 นาที | 2 |
| Validation | 15 นาที | 0 |
| Publish | 10 นาที | 1 |

ค่าเหล่านี้เป็นเพดานเริ่มต้น ต้องปรับจากเวลาที่วัดได้จริงหลังรัน 3-5 รอบ

## 10. Monitoring และการแจ้งเตือน

ทุก run ต้อง log อย่างน้อย:

- `batch_id` และ Airflow `run_id`
- source file ใหม่/เปลี่ยน/หาย
- API status, snapshot checksum และจำนวนคำ
- จำนวน extraction rows, frequency rows และ sentence rows
- HSK match rate และสัดส่วนแต่ละระดับ
- task duration และจำนวน retry
- last successful batch ที่ production ใช้อยู่

ตั้ง `on_retry_callback` สำหรับ warning และ `on_failure_callback` สำหรับ error โดยข้อความต้องมี DAG ID, task ID, run ID, error แบบย่อ และลิงก์ไป log

ช่วง local development ให้บันทึก structured log ก่อน เมื่อ deploy จริงค่อยต่อ Email หรือ Slack Notifier โดยเก็บ credential ใน Airflow Connection/secret backend ไม่ใส่ใน DAG

## 11. Runbook เมื่อเกิดปัญหา

### API ล้ม

1. ดู HTTP status และ freshness ของ snapshot ล่าสุด
2. ถ้าเป็น 429/5xx รอ retry
3. ถ้า 401/403 แก้ credential แล้ว clear เฉพาะ task ที่ล้ม
4. ห้าม mark success ด้วยมือถ้ายังไม่ได้ยืนยัน snapshot

### PDF/audio บางไฟล์เสีย

1. ดู manifest เพื่อระบุไฟล์
2. ย้ายผลไป quarantine โดยเก็บต้นฉบับไว้
3. แก้ไฟล์หรือกำหนด exclusion พร้อมเหตุผล
4. clear ตั้งแต่ extract task ของ batch เดิม เพื่อให้ downstream สร้างใหม่จาก staging เดิม

### Transform quality gate ล้ม

1. เปรียบเทียบ quality report กับ last successful batch
2. ตรวจ tokenizer config, wordlist checksum และตัวอย่างคำที่เปลี่ยนระดับ
3. แก้โค้ด/config แล้วรัน regression tests
4. clear ตั้งแต่ transform task ห้าม rerun เฉพาะ load

### Database load ล้ม

1. ยืนยันว่า staging transaction rollback แล้ว
2. ตรวจ connection, lock และพื้นที่ disk
3. clear เฉพาะ staging load ได้ เพราะ task ต้อง idempotent
4. ถ้า publish ล้ม ห้ามแก้ production ด้วย SQL รายจุด ให้ใช้ transaction/rollback procedure

## 12. ลำดับการลงมือทำ

### Phase 1 — Wordlist Extract

- สร้าง `etl/extract_wordlist.py`
- ย้าย API pagination และ snapshot logicออกจาก Notebook 01
- เพิ่ม checksum, metadata และ quality checks
- เพิ่ม task `refresh_wordlist_if_changed`
- ทดสอบ API success, timeout, 401, response ผิด schema และ no-change

เกณฑ์ผ่าน: API ล้มแล้ว production snapshot เดิมยังอยู่ และ retry ทำงานเฉพาะ error ชั่วคราว

### Phase 2 — Incremental PDF/audio Extract

- สร้าง inventory/manifest module
- แยก PDF extraction และ audio transcription เป็น task
- เพิ่ม checkpoint รายไฟล์
- รวมผลเป็น `raw_extractions.parquet` ใน staging
- เพิ่ม quarantine และ validation

เกณฑ์ผ่าน: เพิ่มไฟล์หนึ่งไฟล์แล้วประมวลผลเฉพาะไฟล์นั้น และไฟล์เสียหนึ่งไฟล์ทำให้ publish ไม่เกิด

### Phase 3 — Transform เป็น Python module

- ย้าย logic ที่ใช้งานจริงจาก Notebook 02 เข้า `etl/`
- ใช้ tokenizer/config เดียวกับ notebook และ Python files
- เพิ่ม regression tests และ quality report
- ให้ notebook เหลือหน้าที่วิเคราะห์/ทดลอง โดย import module เดียวกับ production

เกณฑ์ผ่าน: output เทียบ baseline ได้, match rate ไม่ถอย และสัดส่วน HSK 1 อยู่ในเกณฑ์

### Phase 4 — Atomic Database Publish

- เพิ่ม staging tables หรือ `batch_id`
- เปลี่ยน loaders ให้เขียน staging
- เพิ่ม validation และ publish transaction
- เพิ่ม API smoke test

เกณฑ์ผ่าน: จงใจทำให้แต่ละจุดล้มแล้ว production ยังเป็น last successful batch เสมอ

### Phase 5 — เปิด Scheduler

- รัน manual ให้ผ่าน 3 รอบ
- สร้าง pools และกำหนด timeout/retry
- เปิด weekly schedule
- เพิ่ม callback/notifier และคู่มือ rerun

เกณฑ์ผ่าน: scheduler ไม่สร้างงานซ้อน, no-change run จบด้วย skipped/success และ failure แจ้งเตือนได้

## 13. Definition of Done

ถือว่า Full ETL พร้อมใช้เมื่อ:

- E, T และ L รันจาก Python modules ภายใต้ Airflow โดยไม่ต้องเปิด Notebook
- ไม่มีการดึงหรือประมวลผลไฟล์เดิมซ้ำโดยไม่จำเป็น
- ทุก task rerun ได้โดยไม่สร้างข้อมูลซ้ำ
- failure ก่อน publish ไม่เปลี่ยน production
- failure หลัง publish มี rollback procedure ที่ทดสอบแล้ว
- quality gates ครอบคลุม source completeness, tokenizer regression, HSK distribution และ database counts
- มี log, timeout, retry, pool และ alert ครบ
- manual run ผ่านอย่างน้อย 3 รอบก่อนเปิด schedule

## 14. CI และ Deploy Gate (ทำหลัง Full ETL เสร็จ)

ช่วงทำแผนและพัฒนา ให้รัน Airflow ในเครื่องก่อน และยังไม่ deploy ระบบ production การ push โค้ดจะต้องไม่ถูกตีความว่า Airflow production ถูก deploy แล้ว เพราะ Airflow Compose เป็น runtime แยกจาก Vercel/Neon

### CI ที่ต้องเพิ่ม

เพิ่ม job `airflow` ใน `.github/workflows/ci-cd.yml` หลังจาก Full ETL มีโค้ดจริงแล้ว โดย job ต้องทำอย่างน้อย:

```text
checkout
  ↓
สร้าง .env ทดสอบจาก .env.example
  ↓
docker compose config --quiet
  ↓
build Airflow image
  ↓
airflow dags list-import-errors
  ↓
รัน DAG/task smoke test
  ↓
ตรวจ quality/unit tests ของ etl/
  ↓
หยุดและล้าง test containers
```

CI ต้อง fail เมื่อเกิดกรณีเหล่านี้:

- DAG import error
- Airflow image build ไม่ผ่าน
- dependency conflict เช่น Airflow กับ SQLAlchemy
- task smoke test ล้ม
- quality gate ของ Extract/Transform ไม่ผ่าน
- Compose syntax หรือ required environment ผิด

ไม่ควรใช้ `|| true` กับ DAG import, smoke test หรือ quality gate เพราะจะทำให้ CI เป็นสีเขียวทั้งที่ pipeline ใช้งานไม่ได้ การยอมให้ warning ไม่บล็อกควรจำกัดเฉพาะ Bandit finding ที่ตั้งใจรับความเสี่ยงและต้องมี issue ติดตาม

### เงื่อนไขก่อน merge

- local Full ETL ผ่าน 3 รอบติดกัน
- ทดสอบ API ล้ม, PDF เสีย, audio เสีย, tokenizer quality fail และ database connection fail แล้ว
- production database ยังไม่เปลี่ยนเมื่อแต่ละ failure case เกิดขึ้น
- GitHub Actions ทุก job ผ่าน
- ไม่มี secret, password, `airflow/logs/`, generated `airflow.cfg` หรือ `simple_auth_manager_passwords.json` อยู่ใน commit

### เงื่อนไขก่อน deploy

ค่อย deploy เมื่อทุกข้อด้านล่างผ่าน:

1. Full ETL code และ staging/publish transaction เสร็จ
2. CI มี Airflow job และผ่านจริงบน commit เดียวกับที่จะ deploy
3. มี backup หรือ rollback procedure ของ production database
4. กำหนด Airflow runtime ที่จะรันจริงแล้ว เช่น VM หรือ managed Airflow พร้อม volume/storage ที่ durable
5. ตั้ง secrets ผ่าน secret manager/connection ไม่ฝังใน Compose หรือ DAG
6. มี schedule, pool, timeout, alert และ runbook พร้อม
7. ทดสอบ deploy ใน environment แยกก่อน production

Vercel deployment ของ API/frontend และการรัน Airflow ETL ควรเป็นคนละ release step แต่ต้องอ้างอิง schema/data contract รุ่นเดียวกัน หาก schema เปลี่ยน ให้ migrate database และตรวจ compatibility ก่อนเปิด DAG รุ่นใหม่

## 15. สิ่งที่ยังไม่ทำในรอบวางแผนนี้

- ยังไม่เปิด schedule อัตโนมัติ
- ยังไม่ deploy Airflow ไป production
- ยังไม่เพิ่ม Airflow CI job จนกว่า E/T และ staging publish จะมี implementation จริง
- ยังไม่เปลี่ยน DAG load-only ที่ผ่านแล้วจนกว่าจะมี Full ETL version ที่ผ่าน acceptance criteria

## อ้างอิง Airflow

- [Airflow Tasks: timeout และ retry policy](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/tasks.html)
- [Airflow Pools](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/pools.html)
- [Airflow Callbacks](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/callbacks.html)
- [Task and Asset State Store](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/task-and-asset-state-store.html)

## Implementation status (2026-08-04)

The implementation for Phases 1-5 is now present in the repository:

- Phase 1: `etl/extract_wordlist.py` provides pagination, retry policy, schema/quality validation, checksum metadata, atomic snapshots, no-change detection, and a bounded invalid-row quarantine. The DAG task is `refresh_wordlist_if_changed`.
- Phase 2: `etl/manifest.py` inventories PDF/audio files by SHA-256, reuses unchanged extraction artifacts across runs, checkpoints each source, validates the raw snapshot, and quarantines failures.
- Phase 3: `etl/transform_batch.py` is the production transform shared by the notebook and DAG configuration. It writes counts plus an atomic quality report and enforces match-rate/HSK1 gates.
- Phase 4: `etl/stage_database.py` creates batch-scoped staging tables and publishes all production tables in one transaction. A failed publish rolls back before commit.
- Phase 5: the DAG has `max_active_runs=1`, task timeouts, exponential retry, pools, opt-in schedule, callback logging/webhook notification, and an optional API smoke test. Compose init creates the three pools. CI validates Compose and DAG syntax.

Verified locally: 27 unit tests pass, Airflow DAG import errors are empty, the API returned 7,410 records with one quarantined malformed row, and the real transform produced match rate 0.882683 with HSK1 occurrence share 0.555734. The approved benchmark baseline is approximately 0.854562, so the default gate is 0.85 and the default HSK1 ceiling is 0.60.

Still required before calling the pipeline production-accepted: provide at least one PDF/audio source set, start the runtime after the Docker daemon clears any stale container-name conflict, verify the application DB host mapping, and complete three end-to-end manual DAG runs. The weekly schedule remains disabled by default (`HSK_AIRFLOW_ENABLE_SCHEDULE=false`); enabling it is intentionally a separate acceptance/deploy action.
