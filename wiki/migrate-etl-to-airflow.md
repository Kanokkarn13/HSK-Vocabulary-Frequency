# คู่มือย้าย Data Pipeline ไป Apache Airflow แบบค่อยเป็นค่อยไป

คู่มือนี้อ้างอิงจากโครงสร้างปัจจุบันของโปรเจกต์ HSK Vocabulary Frequency และตั้งใจให้ใช้ฝึกเขียน DAG ด้วยตนเอง จึงให้ทั้งแนวทาง โครง DAG และจุดตรวจ แต่เว้นบางส่วนเป็น `TODO` ไว้ให้ลองทำ

ก่อนเริ่มสร้าง DAG ให้ทำตาม [แผนเตรียม Pipeline ก่อนย้ายไป Airflow](pre-airflow-pipeline-plan.md) โดยเฉพาะการเก็บ baseline และทดลองแก้ Jieba เพื่อให้ Airflow ไม่ไปรัน transform ที่ผลยังไม่นิ่ง

> เป้าหมายรอบแรก: ให้ Airflow เรียกงานเดิมได้อย่างน่าเชื่อถือก่อน ยังไม่ต้องรีบเขียน ETL ใหม่ทั้งหมด

## 1. เข้าใจของเดิมก่อน

ปัจจุบัน pipeline มี 2 เส้นทางหลัก

### เส้นทาง batch ที่ใช้งานจริง

```text
PDF และ audio
    ↓
notebooks/01_extract_raw_text.ipynb
    ↓
data/raw/raw_extractions.parquet
    ↓
notebooks/02_segment_and_count.ipynb
    ↓
data/processed/word_counts.parquet
    ↓
etl/load_word_counts.py ──→ PostgreSQL

data/raw/raw_extractions.parquet
    ↓
etl/load_sentences.py ────→ PostgreSQL
```

### เส้นทางเพิ่มข้อสอบรายไฟล์

`etl/pipeline.py` อ่าน PDF หรือ audio แล้ว segment, count และเขียนฐานข้อมูลโดยตรง เหมาะกับการเพิ่มข้อสอบใหม่ทีละชุด แต่ยังทำงานไม่เหมือน notebook batch ทุกจุด เช่น notebook มี OCR fallback, การลบเสียงที่พูดซ้ำ, fallback decomposition และ CC-CEDICT เพิ่มเติม

ดังนั้น **อย่าเพิ่งแทน batch pipeline ด้วย `etl/pipeline.py` แล้วคิดว่าผลจะเหมือนเดิม**

## 2. DAG ที่แนะนำ

รอบฝึกครั้งแรกให้ใช้ไฟล์ Parquet ที่ notebook สร้างไว้แล้ว และย้ายเฉพาะขั้น load เข้า Airflow:

```text
check_input_files
       ↓
load_word_counts
       ↓
load_sentences
       ↓
validate_database
```

แม้ `load_sentences` จะพึ่งเฉพาะ `raw_extractions.parquet` แต่ควรเรียงหลัง `load_word_counts` ในรอบแรก เพราะทั้งสอง task เขียนฐานข้อมูลเดียวกัน และ `load_sentences.py` ลบทั้งตารางก่อนโหลดใหม่ การรันขนานกันยังไม่ให้ประโยชน์มากพอสำหรับช่วงฝึก

เมื่อรอบแรกนิ่งแล้ว ค่อยย้าย logic จาก notebook เป็น Python module และขยาย DAG เป็น:

```text
inventory
   ├── extract_pdf ───────┐
   └── transcribe_audio ──┤
                          ↓
                 validate_extraction
                          ↓
                 segment_and_count
                          ↓
                    quality_check
                          ↓
                  load_word_counts
                          ↓
                   load_sentences
                          ↓
                  validate_database
```

## 3. สิ่งที่ Airflow ควรทำ และไม่ควรทำ

Airflow ควรรับผิดชอบเรื่อง:

- เวลาและเงื่อนไขการเริ่มงาน
- ลำดับและ dependency ของ task
- retry, timeout, log และสถานะสำเร็จ/ล้มเหลว
- การสั่งรันย้อนหลังหรือรันใหม่เฉพาะ task

ส่วน logic เช่น อ่าน PDF, ตัดคำ และเขียนฐานข้อมูล ควรอยู่ใน `etl/` เหมือนเดิม DAG ควรบางและอ่านง่าย ไม่ควรนำโค้ดแปลงข้อมูลก้อนใหญ่มาใส่ตรง ๆ ในไฟล์ DAG

## 4. เตรียมโครงสร้างไฟล์

สร้างโฟลเดอร์ดังนี้:

```text
airflow/
├── dags/
│   └── hsk_batch_pipeline.py
├── logs/                 # ไม่ควร commit
├── plugins/
├── config/
├── Dockerfile
└── docker-compose.airflow.yml
```

เพิ่มรายการเหล่านี้ใน `.gitignore`:

```gitignore
airflow/logs/
airflow/config/airflow.cfg
```

แนะนำให้แยก `docker-compose.airflow.yml` จาก `docker-compose.yml` เดิมในช่วงฝึก จะหยุดหรือล้าง Airflow ได้โดยไม่กระทบ database และ API เดิม

## 5. เตรียม Airflow ด้วย Docker

ใช้ Docker Compose quick start จากเอกสาร Airflow เป็นฐาน ไม่ควรเขียน service ทั้งหมดจากความจำ เพราะ Airflow มี scheduler, DAG processor, API server, worker, triggerer, metadata database และ Redis ที่ต้องตั้งค่าให้ตรงกัน

เอกสารทางการ: [Running Airflow in Docker](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/)

ข้อควรรู้สำหรับโปรเจกต์นี้:

1. Airflow ต้องมี **metadata database ของตัวเอง** อย่าใช้ schema เดียวกับ `hsk_frequency`
2. PostgreSQL ของแอปเดิมเปิด host port `5432` อยู่แล้ว ถ้าสร้าง Postgres ของ Airflow อีกตัว ห้าม map port ซ้ำกัน ใช้เฉพาะ Docker network ภายใน หรือใช้ host port อื่น เช่น `5433`
3. ทุก Airflow worker ที่รัน task ต้องเห็นโฟลเดอร์เดียวกัน:

```yaml
volumes:
  - ../:/opt/airflow/project
  - ./dags:/opt/airflow/dags
  - ./logs:/opt/airflow/logs
```

4. ตั้ง working Python path ให้ import `etl` ได้ เช่น:

```yaml
environment:
  PYTHONPATH: /opt/airflow/project
```

5. จาก container ห้ามใช้ `DB_HOST=localhost` เพื่อหา Postgres อีก container ให้ใช้ชื่อ service เช่น `db`
6. ถ้า Airflow Compose และ app Compose อยู่คนละไฟล์ ต้องทำให้ทั้งสองอยู่ Docker network เดียวกัน หรือให้ Airflow ต่อฐานข้อมูลผ่าน `host.docker.internal`

### Custom image

Airflow image ปกติไม่มี dependency ทั้งหมดของโปรเจกต์ จึงควรสร้าง `airflow/Dockerfile` ของตัวเอง แนวทาง:

```dockerfile
FROM apache/airflow:<เลือกเวอร์ชันที่ต้องการ>

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements/etl.txt /tmp/requirements-etl.txt

# TODO: pin apache-airflow ให้เป็นเวอร์ชันเดียวกับ base image ระหว่าง pip install
RUN pip install --no-cache-dir -r /tmp/requirements-etl.txt
```

Airflow แนะนำให้ pin `apache-airflow` เป็นเวอร์ชันเดียวกับ base image ตอนติดตั้ง dependency เพิ่ม เพื่อป้องกัน pip เปลี่ยนเวอร์ชัน Airflow โดยไม่ตั้งใจ

สำหรับรอบแรกที่เรียกแค่ loader สามารถทำ requirements ชุดเล็กก่อน ได้แก่ `pandas`, `pyarrow`, `sqlalchemy`, `psycopg2-binary` และ `python-dotenv` จะช่วยลดขนาด image ได้มาก จากนั้นค่อยเพิ่ม Whisper, ffmpeg และ OCR เมื่อย้าย extract task จริง

## 6. ตั้งค่า secret และ connection

อย่าเขียน password ลงใน DAG หรือ commit `.env`

สำหรับช่วงฝึกง่ายที่สุดคือส่งตัวแปรเดิมให้ worker:

```text
DB_HOST=db
DB_PORT=5432
DB_NAME=hsk_frequency
DB_USER=hsk_user
DB_PASSWORD=...
DB_SSLMODE=
```

เมื่อเข้าใจพื้นฐานแล้ว ค่อยเปลี่ยนไปใช้ Airflow Connection เช่น connection id ชื่อ `hsk_postgres` ข้อดีคือจัดการ credential แยกจากโค้ดและเปลี่ยนปลายทางได้ง่าย

## 7. เขียน DAG แรก

สร้าง `airflow/dags/hsk_batch_pipeline.py` แล้วลองเติม `TODO` ในโครงนี้:

```python
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_DIR = Path("/opt/airflow/project")
DATA_DIR = PROJECT_DIR / "data"


@dag(
    dag_id="hsk_batch_pipeline",
    start_date=datetime(2026, 1, 1),
    schedule=None,          # เริ่มจากกด Run เองก่อน
    catchup=False,
    max_active_runs=1,     # กันการโหลดทับกันสองรอบ
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["hsk", "etl", "learning"],
)
def hsk_batch_pipeline():

    @task
    def check_input_files() -> list[str]:
        required = [
            DATA_DIR / "raw" / "raw_extractions.parquet",
            DATA_DIR / "processed" / "word_counts.parquet",
            DATA_DIR / "processed" / "hsk_wordlist.csv",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing input files: {missing}")
        return [str(path) for path in required]

    @task
    def load_word_counts(_: list[str]) -> None:
        # import ภายใน task ทำให้ DAG parser ไม่ต้องโหลด pandas/SQLAlchemy ทุกครั้ง
        from etl.load_word_counts import run
        run()

    @task
    def load_sentences() -> None:
        from etl.load_sentences import run
        run()

    @task
    def validate_database() -> None:
        # TODO:
        # 1. ใช้ etl.load_to_db.get_engine()
        # 2. SELECT COUNT(*) จาก exam_sources, word_frequencies,
        #    frequency_aggregates และ exam_sentences
        # 3. raise ValueError ถ้าตารางสำคัญมี 0 rows
        # 4. log จำนวน rows เพื่อให้ตรวจใน Airflow UI ได้
        raise NotImplementedError("ลองเขียน data quality check ตรงนี้")

    checked_files = check_input_files()
    counts_done = load_word_counts(checked_files)
    sentences_done = load_sentences()

    # TODO: กำหนด dependency ให้เป็น
    # counts_done -> sentences_done -> validate_database()


hsk_batch_pipeline()
```

แบบฝึกหัดสำคัญ:

- ทำไม `schedule=None` เหมาะกับรอบแรก?
- ถ้า `load_word_counts` สำเร็จ แต่ `load_sentences` ล้มเหลว แล้วกด retry จะเกิดอะไรขึ้น?
- เพราะเหตุใด `max_active_runs=1` จึงสำคัญกับ `DELETE FROM exam_sentences`?
- ลองเพิ่ม `execution_timeout` ให้ task ที่อาจค้าง

## 8. ตรวจว่า DAG โหลดได้

หลัง build และ start Airflow แล้ว ให้ตรวจตามลำดับ:

```powershell
docker compose -f airflow/docker-compose.airflow.yml build
docker compose -f airflow/docker-compose.airflow.yml up airflow-init
docker compose -f airflow/docker-compose.airflow.yml up -d
docker compose -f airflow/docker-compose.airflow.yml ps
```

เปิด `http://localhost:8080` แล้วตรวจว่าเห็น `hsk_batch_pipeline`

ถ้าไม่เห็น DAG ให้ดู parse error:

```powershell
docker compose -f airflow/docker-compose.airflow.yml exec airflow-scheduler airflow dags list-import-errors
```

จากนั้นทดสอบทีละ task ก่อน:

```powershell
docker compose -f airflow/docker-compose.airflow.yml exec airflow-scheduler `
  airflow tasks test hsk_batch_pipeline check_input_files 2026-08-04
```

ชื่อ service อาจเป็น `airflow-worker` หรือชื่ออื่นตาม Compose ที่เลือกใช้ ให้ตรวจด้วย `docker compose ... ps`

## 9. วิธีทดสอบอย่างปลอดภัย

อย่าเริ่มด้วย Neon หรือฐานข้อมูล production ให้ใช้ PostgreSQL local ก่อน เพราะ loader มีพฤติกรรมเปลี่ยนข้อมูลจริง:

- `load_word_counts.py` upsert ข้อมูลและ rebuild aggregate
- `load_sentences.py` สั่ง `DELETE FROM exam_sentences` แล้วโหลดใหม่ทั้งหมด

ลำดับทดสอบที่แนะนำ:

1. backup หรือใช้ database local ใหม่
2. รัน `check_input_files`
3. รัน `load_word_counts`
4. เปรียบเทียบจำนวน row ก่อนและหลัง
5. รัน `load_sentences`
6. รัน DAG เดิมซ้ำอีกครั้ง
7. ตรวจว่าจำนวน row ไม่เพิ่มผิดปกติ การรันซ้ำได้โดยผลไม่เพี้ยนเรียกว่า idempotent
8. จงใจเปลี่ยน path input ให้ผิดหนึ่งครั้ง เพื่อดู log, retry และสถานะ failed
9. แก้ path แล้วกด clear/retry เฉพาะ task ไม่ต้องรันทั้ง DAG ใหม่

## 10. ย้าย Notebook ออกจาก pipeline ทีละส่วน

Airflow สั่ง notebook ได้ แต่สำหรับระยะยาวควรย้าย logic ที่ใช้จริงออกจาก notebook มาเป็น Python module เพราะทดสอบง่ายกว่า อ่าน diff ง่ายกว่า และ reuse ได้

### ระยะ A: แยก notebook 01

สร้าง module เช่น:

```text
etl/
├── inventory_sources.py
├── extract_raw_text.py
├── validate_extractions.py
└── fetch_wordlist.py
```

แต่ละไฟล์ควรมี `run(...)` ที่รับ input ชัดเจนและคืนค่าเล็ก ๆ เช่น path, จำนวนไฟล์ หรือ summary เท่านั้น อย่าส่ง DataFrame ใหญ่ผ่าน XCom ให้บันทึกเป็น Parquet แล้วส่งแค่ path

จุดที่ต้องรักษาจาก notebook เดิม:

- การ deduplicate 135 ไฟล์ให้เหลือ 130 ไฟล์
- OCR fallback ทั้งกรณี text ว่าง, sparse และมี `(cid:N)` มาก
- Whisper ใช้ `language="zh"`
- completeness validation แยก `full_exam` กับ `instruction_sheet`
- wordlist cache และ `FORCE_REFRESH`

### ระยะ B: แยก notebook 02

สร้าง `etl/transform_word_counts.py` และย้ายทีละฟังก์ชัน พร้อม unit test

จุดที่ต้องรักษา:

- dedupe ประโยคเสียงซ้ำก่อนตัดคำ
- traditional → simplified
- jieba segmentation และ CJK-only filter
- HSK direct match
- decomposition fallback และ `match_pattern`
- CC-CEDICT cache/cross-check
- schema ของ `word_counts.parquet`

อย่าพยายามย้ายทั้ง notebook ใน commit เดียว ให้ย้ายหนึ่งฟังก์ชัน รันเทียบ output กับของเดิม แล้วค่อยไปส่วนถัดไป

### ระยะ C: เปลี่ยน DAG ให้เรียก module ใหม่

เมื่อ Python module ให้ผลเท่า notebook แล้ว จึงเพิ่ม task:

```python
raw_path = extract_raw_text()
validated_path = validate_extractions(raw_path)
counts_path = segment_and_count(validated_path)
quality_check(counts_path)
load_word_counts(counts_path)
```

Airflow dependency ควรบอกลำดับงาน ส่วน path ที่คืนจาก task ใช้บอกว่า artifact อยู่ที่ไหน ไม่ควรใช้ XCom เก็บเนื้อหา Parquet

## 11. งาน Whisper ควรจัดการต่างจาก task ทั่วไป

Whisper `medium` ใช้ CPU/RAM/GPU มากและใช้เวลานาน จึงไม่ควรปล่อยให้หลาย task แย่ง resource กัน

เมื่อเริ่มย้าย audio:

1. สร้าง Airflow Pool เช่น `whisper_pool`
2. ให้ pool มี 1 slot ในเครื่องฝึก
3. กำหนด task transcription ให้ใช้ pool นี้
4. ตั้ง timeout ที่สมเหตุสมผล
5. cache transcript รายไฟล์ เพื่อให้ retry ไม่ต้องถอดเสียงไฟล์ที่สำเร็จแล้ว
6. ถ้าใช้ GPU ให้ worker ที่รัน task เข้าถึง GPU ได้จริง

ควรแยก PDF extraction กับ audio transcription เป็นคนละ task branch เพราะ resource และเวลารันต่างกันมาก

## 12. Data quality checks ที่ควรมี

เริ่มจาก checks ที่เข้าใจง่าย:

- input ทั้ง 3 ไฟล์มีอยู่และขนาดมากกว่า 0
- `raw_extractions.parquet` ไม่มี key `(exam_id, source_type)` ซ้ำ
- source type มีเฉพาะ `reading` และ `listening`
- `word_counts.parquet` ไม่มี count ติดลบหรือเป็น null
- หลังโหลด `exam_sources` ต้องไม่เป็น 0
- ทุก `(exam_id, source_type)` ใน `word_frequencies` ต้องมีใน `exam_sources`
- aggregate ของคำหนึ่งคำควรเท่ากับผลรวมจาก `word_frequencies`
- จำนวน exam และ row ไม่ลดลงแรงผิดปกติจาก baseline โดยไม่มีเหตุผล

ถ้า check ไม่ผ่าน ให้ `raise ValueError` เพื่อหยุด DAG ก่อนข้อมูลที่ผิดไหลต่อ

## 13. เรื่อง schedule

เริ่มจาก `schedule=None` และกดรันเอง เมื่อ pipeline นิ่งแล้วค่อยเลือก schedule ตามแหล่งข้อมูลจริง

- ถ้ามีข้อสอบใหม่ไม่แน่นอน: ใช้ manual trigger หรือ event จากระบบอื่น
- ถ้ามีไฟล์เข้าทุกสัปดาห์: ใช้ schedule รายสัปดาห์
- ถ้าต้องรอไฟล์: ใช้ Sensor แต่ต้องกำหนด timeout และโหมดรอให้เหมาะสม

อย่าตั้ง `@daily` เพียงเพราะทำได้ หาก upstream ไม่มีข้อมูลใหม่ จะเสีย resource กับงาน Whisper และเพิ่มโอกาสเขียนฐานข้อมูลซ้ำโดยไม่จำเป็น

## 14. Definition of Done สำหรับการย้ายรอบแรก

ถือว่ารอบแรกสำเร็จเมื่อ:

- Airflow UI เห็น DAG โดยไม่มี import error
- กดรันด้วยมือแล้วทุก task สำเร็จ
- task log บอก input และจำนวน row ที่โหลดได้
- รันซ้ำแล้วผลใน database ไม่เพิ่มหรือหายผิดปกติ
- retry เฉพาะ task ที่ล้มเหลวได้
- password ไม่อยู่ใน DAG หรือ Git
- Airflow metadata DB แยกจาก application DB
- มี data quality task ปิดท้าย
- test เดิมของ `etl/` ยังผ่าน

## 15. แผนฝึก 5 รอบ

1. **รอบ 1:** เปิด Airflow และทำ DAG `hello_world`
2. **รอบ 2:** ทำ `check_input_files` และลองทำให้ fail
3. **รอบ 3:** ต่อ `load_word_counts` และ `load_sentences`
4. **รอบ 4:** เขียน `validate_database` เองและทดสอบ rerun
5. **รอบ 5:** เลือกหนึ่งส่วนเล็กจาก notebook เช่น `inventory` หรือ `segment()` ย้ายเป็น Python task พร้อม unit test

หลังครบ 5 รอบ คุณจะได้ฝึกแกนหลักของ Airflow ได้แก่ DAG, task, dependency, retry, log, schedule, connection, idempotency และ data quality โดยยังไม่ต้องแบกความซับซ้อนของ OCR/Whisper ทั้งหมดตั้งแต่วันแรก

## เอกสารอ่านต่อ

- [Airflow: Running in Docker](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/)
- [Airflow: First Workflow](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/fundamentals.html)
- [Airflow: DAG concepts](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)
- [Airflow: Task concepts](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/tasks.html)
- เอกสาร pipeline ของ repo: `wiki/etl-pipeline.md`
- schema ฐานข้อมูล: `db/schema.sql`
