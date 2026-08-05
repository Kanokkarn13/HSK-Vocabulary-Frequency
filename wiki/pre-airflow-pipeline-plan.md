# แผนเตรียม Data Pipeline ก่อนย้ายไป Airflow

เอกสารนี้เป็นแผนงานก่อนเริ่มสร้าง Airflow DAG จริง เป้าหมายคือทำให้ extract และ transform ให้ผลถูกต้อง ทดสอบได้ และรันซ้ำได้ก่อน จากนั้น Airflow จะมีหน้าที่จัดลำดับและควบคุมการรันเท่านั้น

## เป้าหมาย

ก่อนย้ายไป Airflow เราต้องตอบได้ว่า:

1. ข้อมูลเข้าและผลลัพธ์ของแต่ละขั้นคืออะไร
2. Jieba ตัดคำดีขึ้นจริง ไม่ได้แค่ทำให้ match rate สูงขึ้น
3. Notebook และ Python module ให้ผลเหมือนกัน
4. pipeline รันซ้ำแล้วข้อมูลไม่เพี้ยน
5. ถ้าข้อมูลผิด pipeline สามารถหยุดก่อน load เข้า database

## ขอบเขตงาน

```text
Phase 0  เก็บ baseline
   ↓
Phase 1  ทดลองและแก้ Jieba
   ↓
Phase 2  แยก transform ออกจาก Notebook
   ↓
Phase 3  แยก extract ออกจาก Notebook
   ↓
Phase 4  กำหนด data contract และ quality checks
   ↓
Phase 5  ทำ pipeline runner และทดสอบ rerun
   ↓
พร้อมย้ายไป Airflow
```

หลักสำคัญคือเปลี่ยนทีละเรื่องและเปรียบเทียบผลทุกครั้ง ถ้าเปลี่ยนการตัดคำ, OCR และ load พร้อมกัน เราจะหาสาเหตุได้ยากเมื่อจำนวนข้อมูลเปลี่ยน

---

## Phase 0 — เก็บผลปัจจุบันเป็น Baseline

### ทำอะไร

เก็บสถิติจาก output ปัจจุบันก่อนแก้ Jieba:

- จำนวน exam ทั้งหมด
- จำนวน token occurrences
- จำนวน unique words
- จำนวนแถวใน `word_counts.parquet`
- direct/decomposed/unmatched match rate
- จำนวนคำหนึ่งอักษร
- top 100 unmatched words
- checksum หรือชื่อ snapshot ของไฟล์ output

ไฟล์ที่ใช้:

```text
data/raw/raw_extractions.parquet
data/processed/hsk_wordlist.csv
data/processed/word_counts.parquet
data/processed/unmatched_words_review.csv
```

### Output ที่ต้องได้

```text
data/validation/baseline_summary.json
data/validation/baseline_top_unmatched.csv
```

### เหตุผล

ถ้าไม่มี baseline เราจะรู้เพียงว่าผล “เปลี่ยน” แต่ไม่รู้ว่า “ดีขึ้น” หรือไม่

### ถือว่าเสร็จเมื่อ

- สร้าง baseline ซ้ำจากไฟล์เดิมแล้วได้ตัวเลขเดิม
- baseline แยกตาม `reading` และ `listening` ได้

---

## Phase 1 — ทดลองและแก้ Jieba

Phase นี้เป็นงานสำคัญที่สุดก่อนย้าย transform ไป Airflow

### 1.1 สร้างชุดประโยคตรวจคำตอบ

สร้างไฟล์:

```text
data/validation/segmentation_cases.csv
```

แนะนำ columns:

| column | ความหมาย |
|---|---|
| `case_id` | รหัสตัวอย่าง |
| `text` | ประโยคหรือช่วงข้อความ |
| `expected_tokens` | คำที่ต้องการ คั่นด้วย `|` |
| `reason` | เหตุผล เช่น คำ HSK ซ้อนกัน, ชื่อคน, OCR noise |
| `source_type` | reading หรือ listening |

ตัวอย่าง:

```csv
case_id,text,expected_tokens,reason,source_type
001,我觉得这个问题很重要,我|觉得|这个|问题|很|重要,คำหนึ่งอักษรซ้อนกับคำหลายอักษร,listening
```

เริ่มจากอย่างน้อย 30 ตัวอย่าง และเพิ่มทุกครั้งที่พบ bug ใหม่ ชุดนี้คือ regression test ที่บอกว่าการแก้รอบใหม่ทำลายเคสเดิมหรือไม่

### 1.2 แยก tokenizer ออกจาก global Jieba

สร้าง module ใหม่:

```text
etl/tokenizer.py
```

ใช้ `jieba.Tokenizer()` ของโปรเจกต์เองแทนการแก้ `jieba` global state เพื่อให้ test แต่ละรอบไม่ปนกัน และควบคุม dictionary/HMM ได้ชัดเจน

interface ที่ควรมี:

```python
def build_tokenizer(wordlist_path, mode, overrides_path=None):
    ...

def segment(text, tokenizer, hmm):
    ...
```

### 1.3 ทดลอง 4 รูปแบบ

ใช้ raw text ชุดเดียวกันทุก experiment:

| Experiment | รายละเอียด |
|---|---|
| A | Jieba ปัจจุบัน, `HMM=True` |
| B | Jieba ปัจจุบัน, `HMM=False` |
| C | Jieba + คำหลายอักษรจาก HSK CSV |
| D | แบบ C + correction rules ที่ยืนยันด้วยมือ |

อย่าโหลด CC-CEDICT ทั้งชุดเข้า Jieba ในรอบนี้ เพราะ Notebook เคยทดลองแล้วและทำให้ segmentation โดยรวมแย่ลง CC-CEDICT ยังใช้ตรวจว่าคำ unmatched เป็นคำจริงหรือไม่ได้ตามเดิม

### 1.4 วิธีใช้ HSK CSV

อ่าน `word` และ `hsk_level` จาก `data/processed/hsk_wordlist.csv` แต่ใช้เฉพาะคำหลายอักษรสำหรับช่วย segmentation ในรอบแรก

เหตุผล:

- คำอักษรเดียวมีโอกาสชนกับคำหลายอักษรสูง
- เราต้องเลือกขอบเขตคำก่อน แล้วจึงใส่ HSK level
- ระดับสูงหรือต่ำไม่ควรเป็นตัวตัดสินว่าจะเลือกคำใด

ทดลอง frequency อย่างน้อย 3 ค่า:

```text
ค่า default ของ Jieba
10,000
100,000
```

ไม่ควรตั้งสูงมากให้ทุกคำทันที เพราะอาจบังคับรวมคำผิดบริบท

### 1.5 เพิ่ม Correction Rules

สร้างไฟล์:

```text
data/wordlist/jieba_overrides.csv
```

รูปแบบที่แนะนำ:

| action | text | tokens | note |
|---|---|---|---|
| `join` | 图书馆 | 图书馆 | ต้องเป็นคำเดียว |
| `split` | ตัวอย่างคำ | คำ1\|คำ2 | ต้องแยกตามบริบทที่ยืนยันแล้ว |

rules ควรมีเฉพาะกรณีที่ตรวจแล้ว ไม่ควรนำ top unmatched ทั้งหมดมาเพิ่มอัตโนมัติ เพราะ unmatched อาจเป็นชื่อคน คำนอก HSK หรือ OCR/ASR noise

### 1.6 เกณฑ์เลือกผลทดลอง

เรียงความสำคัญดังนี้:

1. accuracy บน `segmentation_cases.csv`
2. เคสที่เคยถูกต้องต้องไม่เสียมาก
3. จำนวน boundary changes ที่ตรวจอธิบายได้
4. HSK coverage ดีขึ้น
5. unmatched rate ลดลง

ห้ามเลือกจาก match rate อย่างเดียว เพราะการรวมตัวอักษรผิดอาจบังเอิญกลายเป็นคำใน HSK CSV และทำให้ตัวเลขดูดีขึ้น

### Output ที่ต้องได้

```text
data/validation/jieba_experiment_summary.csv
data/validation/jieba_boundary_changes.csv
data/validation/segmentation_cases.csv
data/wordlist/jieba_overrides.csv
etl/tokenizer.py
tests/test_tokenizer.py
```

`jieba_boundary_changes.csv` ควรบอกอย่างน้อย:

- exam id
- source type
- text snippet
- tokens เดิม
- tokens ใหม่
- match type เดิม/ใหม่

### ถือว่าเสร็จเมื่อ

- ชุดตัวอย่างผ่านตามเกณฑ์ที่กำหนด เช่นอย่างน้อย 95%
- ไม่มี regression ร้ายแรงในคำที่มีความถี่สูง
- ผลเหมือนเดิมทุกครั้งเมื่อ config เหมือนกัน
- ได้ tokenizer mode ที่เลือกใช้จริงเพียงหนึ่งแบบ

### ผล benchmark รอบแรกจากข้อมูลจริง

รัน `python -m scripts.evaluate_jieba` กับ `data/raw/raw_extractions.csv` จำนวน 130 ไฟล์ ได้ผลดังนี้:

| mode | single-char share | HSK match rate | level 1 / all tokens |
|---|---:|---:|---:|
| baseline, HMM=True | 47.93% | 82.92% | 54.43% |
| baseline, HMM=False | 55.45% | 84.91% | 56.14% |
| HSK merge, HMM=True | **47.70%** | 82.89% | **54.34%** |
| HSK merge, HMM=False | 55.20% | 84.89% | 56.02% |

ข้อสรุป:

- ไม่เลือก `HMM=False` แม้ match rate สูงขึ้น เพราะเพิ่มคำเดี่ยวและสัดส่วนระดับ 1 อย่างชัดเจน
- เลือก `HMM=True` เป็นค่าเริ่มต้น
- ใช้ HSK merge แบบ local longest-match เป็นตัวแก้ boundary ที่ Jieba แยกเกิน เช่นคำหลายอักษรที่อยู่ใน wordlist
- HSK merge ช่วยเพียงเล็กน้อย จึงไม่ควรอ้างว่าสามารถแก้สัดส่วนระดับ 1 ได้ทั้งหมด
- สัดส่วนระดับ 1 สูงส่วนหนึ่งเป็นข้อมูลจริงจากคำฟังก์ชันที่ใช้บ่อย เช่น `的`, `了`, `我`, `你`, `是` ไม่ใช่หลักฐานว่า Jieba ผิดทุกกรณี

ตัวเลขนี้เป็นการเลือกจาก proxy metrics ยังไม่ใช่ accuracy แบบมี gold-standard segmentation เพราะ repo ยังไม่มี annotation ว่าทุกประโยคควรตัดเป็นคำใด การยืนยันขั้นสุดท้ายจึงต้องเพิ่มตัวอย่างใน `segmentation_cases.csv` แล้วตรวจ expected tokens ด้วยคน

รายงานละเอียดอยู่ใน `data/validation/jieba/summary.csv` และรายการ boundary ที่เปลี่ยนอยู่ในไฟล์ `*_boundary_changes.csv` การรันซ้ำจะสร้างรายงานใหม่โดยไม่เขียนทับ `word_counts.parquet`

### ผลทดลอง DP รอบแรก

เพิ่มโหมด `hsk_dp_hmm_true` และชุดตัวอย่าง 20 ประโยคใน `data/validation/segmentation_cases.csv` ผลคือ constrained DP เพิ่ม HSK match rate บน raw corpus เป็น 85.46% แต่เพิ่มคำเดี่ยวเป็น 48.38% และได้ boundary F1 บนชุดตัวอย่างเพียง 0.927 เทียบกับ HSK merge 0.957 จึง **ยังไม่เปิดใช้ DP ใน Notebook หรือ pipeline**

มีการทดลอง objective แบบ maximize HSK-covered characters ตรง ๆ ด้วย แต่ถูกยกเลิก เพราะแม้ HSK match rate ขึ้นถึงประมาณ 96% คำเดี่ยวกลับพุ่งเป็นประมาณ 65.5% และระดับ 1 เป็นประมาณ 64.8% แสดงว่าตัววัดดังกล่าวสามารถถูกทำให้ดูดีด้วยการแตก compound เป็นตัวอักษรระดับ 1 จำนวนมาก จึงไม่ใช่ objective ที่ปลอดภัย

ข้อสรุปนี้สำคัญ: การทำให้คำที่ match HSK มากขึ้นไม่ได้แปลว่าตัดคำถูกขึ้นเสมอไป ชุดตัวอย่างต้องได้รับการทบทวนโดยคนและเพิ่มกรณีที่มีบริบทกำกวมก่อนทดลอง DP อีกครั้ง

### HSK component attribution

เพิ่ม `etl/hsk_components.py` เพื่อแยกการนับ HSK ออกจากการตัดคำ โดย token ที่ไม่ตรง HSK จะถูกแตกได้ก็ต่อเมื่อครอบคลุมด้วยคำ HSK ทั้งหมดและมีคำหลายอักษรอย่างน้อยหนึ่งคำ จึงไม่แตก noise เป็นตัวอักษรระดับ 1 แบบเหมาเข่ง

เมื่อนับเฉพาะ token ที่เดิมเป็น `unmatched` พบ token ที่แตกได้อย่างปลอดภัย 543 unique tokens ครอบคลุม 2,689 raw occurrences หรือประมาณ 21.5% ของ unmatched occurrences (เพิ่ม coverage ของทั้ง corpus ราว 0.97 percentage point) ตัวอย่างที่มีผลสูงคือ `会议室 → 会议 | 室`, `上下班 → 上 | 下班`, `年轻人 → 年轻 | 人`, `谢谢您 → 谢谢 | 您` รายละเอียดอยู่ใน `data/validation/hsk_components/`

Notebook 02 จะสร้าง artifact เพิ่มชื่อ `hsk_component_counts.parquet/csv` โดยยังไม่เขียนทับ `word_counts.parquet` จนกว่าจะตรวจ component mapping ชุดนี้เสร็จ

---

## Phase 2 — แยก Transform ออกจาก Notebook 02

### ทำอะไร

ย้าย logic จาก `notebooks/02_segment_and_count.ipynb` มาเป็น Python modules โดยยังใช้ Notebook สำหรับวิเคราะห์และแสดงผลได้

โครงสร้างที่แนะนำ:

```text
etl/
├── clean_listening_text.py
├── tokenizer.py
├── hsk_matcher.py
├── transform_word_counts.py
└── validate_word_counts.py
```

ลำดับ transform:

```text
raw text
   ↓
dedupe listening repetitions
   ↓
traditional → simplified
   ↓
HSK-aware Jieba segmentation
   ↓
count per (exam_id, source_type)
   ↓
direct HSK match
   ↓
decomposition fallback
   ↓
CC-CEDICT cross-check
   ↓
quality checks
   ↓
word_counts.parquet
```

### กติกาในการแยกโค้ด

- แต่ละฟังก์ชันรับ input และคืน output ชัดเจน
- หลีกเลี่ยงตัวแปร global จาก Notebook
- ห้ามให้ module แสดง plot ระหว่าง production run
- plot และ exploratory analysis ให้อยู่ใน Notebook ต่อได้
- config เช่น `HMM`, word frequency และ path ต้องส่งผ่าน argument หรือ config file
- ใช้ tokenizer เดียวกันทั้ง Notebook, CLI และ Airflow ในอนาคต

### การเปรียบเทียบ

ให้รัน Notebook เดิมและ module ใหม่ด้วย input snapshot เดียวกัน แล้วตรวจ:

- schema และ data type เท่ากัน
- จำนวน exam เท่ากัน
- ไม่มี key `(word, exam_id, source_type)` ซ้ำ
- ผลที่เปลี่ยนต้องมาจาก Jieba improvement ที่อยู่ในรายงาน

### ถือว่าเสร็จเมื่อ

- สร้าง `word_counts.parquet` ได้โดยไม่ต้องเปิด Notebook
- test ครอบคลุม cleaning, tokenization, matching และ decomposition
- Notebook เปลี่ยนมาเรียก module ใหม่แทนการมี logic ซ้ำ

---

## Phase 3 — แยก Extract ออกจาก Notebook 01

ทำหลัง transform นิ่งแล้ว เพราะ OCR และ Whisper ใช้ resource สูงและทดสอบช้ากว่า

โครงสร้างที่แนะนำ:

```text
etl/
├── inventory_sources.py
├── extract_pdf.py
├── transcribe_audio.py
├── fetch_wordlist.py
├── validate_extractions.py
└── extract_raw_text.py
```

### สิ่งที่ต้องรักษาจาก Notebook

- deduplicate source files
- parse `exam_id`, HSK level และ source type
- PDF extraction ด้วย pdfplumber
- OCR fallback เมื่อ text ว่าง, sparse หรือมี `(cid:N)` มาก
- Whisper กำหนดภาษาจีน
- completeness checks ของข้อสอบแต่ละชนิด
- cache transcript และ wordlist snapshot

### ทำให้ retry ได้อย่างประหยัด

อย่าเขียน transcript ของทุกไฟล์ตอนจบงานก้อนเดียว ให้ cache รายไฟล์ เมื่อไฟล์ที่ 60 ล้มเหลว retry จะได้ไม่ต้องถอดเสียง 59 ไฟล์แรกใหม่

### ถือว่าเสร็จเมื่อ

- สร้าง `raw_extractions.parquet` ได้โดยไม่ต้องเปิด Notebook
- rerun แล้วข้ามไฟล์ที่ cache ถูกต้อง
- completeness validation หยุดงานเมื่อจำนวนไฟล์หรือ section ผิด

---

## Phase 4 — กำหนด Data Contract และ Quality Checks

สร้างเอกสารหรือ schema สำหรับ artifact สำคัญ

### `raw_extractions.parquet`

อย่างน้อยต้องมี:

```text
exam_id
source_type
hsk_level
filename
text
```

กฎ:

- `(exam_id, source_type)` ต้องไม่ซ้ำ
- `source_type` ต้องเป็น `reading` หรือ `listening`
- `text` ต้องไม่ว่าง

### `word_counts.parquet`

อย่างน้อยต้องมี:

```text
word
level
exam_id
hsk_level
source_type
count
match_pattern
effective_level
match_type
```

กฎ:

- `(word, exam_id, source_type)` ต้องไม่ซ้ำ
- `count` ต้องเป็นจำนวนเต็มมากกว่า 0
- `match_type` ต้องเป็น `direct`, `decomposed` หรือ `unmatched`
- direct match ต้องมี level
- ทุก exam ต้องอ้างถึง raw extraction ที่มีอยู่

Quality check ต้อง `raise` exception เมื่อผิด ไม่ควรแค่พิมพ์ warning แล้วปล่อย load ต่อในกรณีที่ทำให้ข้อมูลเสีย

---

## Phase 5 — สร้าง Pipeline Runner ก่อน Airflow

สร้าง CLI กลาง เช่น:

```text
python -m etl.batch_pipeline --from-step transform --to-step validate
```

ตัว runner ควรเรียกฟังก์ชันตามลำดับ:

```python
extract()
validate_extraction()
transform()
validate_word_counts()
load_word_counts()
load_sentences()
validate_database()
```

runner ไม่ต้องมี schedule หรือ retry ซับซ้อน จุดประสงค์คือพิสูจน์ว่า pipeline ทำงานครบโดยไม่พึ่ง Notebook เมื่อ runner นี้นิ่งแล้ว การเปลี่ยนแต่ละฟังก์ชันให้เป็น Airflow task จะตรงไปตรงมา

### Rerun tests

ทดสอบอย่างน้อย:

1. รันครบหนึ่งรอบกับ local database
2. บันทึกจำนวน rows และ checksums
3. รันซ้ำด้วย input เดิม
4. ตรวจว่าผลไม่เพิ่มหรือหายผิดปกติ
5. ทำให้ transform ล้มเหลว แล้วตรวจว่า load ไม่ทำงาน
6. แก้ข้อผิดพลาดและเริ่มจาก step ที่ล้มเหลวได้

### ถือว่าเสร็จเมื่อ

- CLI รันครบทุกขั้นได้
- สามารถเลือกเริ่มใหม่จากบาง step
- rerun ให้ผลเท่าเดิม
- error ใน quality check หยุดก่อน database load

---

## ลำดับงานแบบเร่งด่วน

ถ้าต้องการให้เร็วที่สุด ให้ทำตามลำดับนี้โดยยังไม่แตะ Airflow:

### รอบที่ 1 — Jieba ที่วัดผลได้

- สร้าง baseline
- สร้าง segmentation cases
- ทดลอง HMM และ HSK dictionary
- เลือก config
- เพิ่ม tokenizer tests

### รอบที่ 2 — Transform ที่ไม่พึ่ง Notebook

- ย้าย Notebook 02 เป็น module
- รัน before/after report
- ให้ Notebook เรียก module ใหม่

### รอบที่ 3 — Safety ก่อน load

- เพิ่ม schema/data quality checks
- ทดสอบ rerun กับ local PostgreSQL
- สร้าง batch runner ชั่วคราว

หลังรอบที่ 3 สามารถเริ่มสร้าง DAG สำหรับ `transform → validate → load` ได้ ส่วน extract/Whisper ย้ายตามภายหลังโดยไม่ขวางการฝึก Airflow

### รอบที่ 4 — Extract และ Whisper

- ย้าย Notebook 01
- ทำ cache รายไฟล์
- แยก PDF กับ audio เพื่อเตรียมเป็นคนละ Airflow task

---

## งานที่ไม่ควรทำพร้อมกัน

- อย่าเปลี่ยน Jieba และ decomposition rules ใน experiment เดียวกัน
- อย่าโหลด CC-CEDICT ทั้งชุดเข้า Jieba เพียงเพื่อเพิ่ม coverage
- อย่าเขียนทับ baseline output โดยไม่มี snapshot หรือ report
- อย่าเริ่มทดสอบกับ Neon/production database
- อย่านำ DataFrame ขนาดใหญ่ไปเตรียมส่งผ่าน Airflow XCom
- อย่าเขียน ETL logic ซ้ำใน Notebook, CLI และ DAG

---

## Definition of Ready สำหรับเริ่ม Airflow

pipeline พร้อมเริ่มย้ายเมื่อผ่านทุกข้อ:

- [ ] มี baseline ก่อนแก้ Jieba
- [ ] มีชุด segmentation regression cases
- [ ] เลือก Jieba/HMM/dictionary config แล้ว
- [ ] มีรายงาน boundary changes
- [ ] transform รันได้โดยไม่เปิด Notebook
- [ ] extract หรืออย่างน้อย input contract มีความชัดเจน
- [ ] artifact schema มี validation
- [ ] load scripts รันซ้ำได้กับ local database
- [ ] pipeline runner รันครบได้
- [ ] secret ไม่อยู่ใน source code
- [ ] test suite ผ่าน

เมื่อครบรายการนี้ Airflow DAG จะทำหน้าที่ orchestrate โค้ดที่เชื่อถือได้ แทนการนำ Airflow มาครอบ Notebook ที่ยังเปลี่ยนผลอยู่
