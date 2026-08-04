# Keep the Airflow version explicit so the scheduler, API server, and workers
# use the same runtime.  Python 3.11 matches this project's ETL environment.
FROM apache/airflow:3.3.0-python3.11

# Keep OS-level media support in the Airflow image so audio extraction is
# reproducible on the scheduler and never depends on a developer laptop.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# These are the ETL dependencies only.  Do not install requirements/etl.txt
# wholesale here because it pins SQLAlchemy independently of Airflow.
RUN pip install --no-cache-dir \
    pandas==3.0.3 \
    pyarrow==24.0.0 \
    pdfplumber==0.11.4 \
    openai-whisper==20250625 \
    jieba==0.42.1 \
    opencc-python-reimplemented==0.1.7 \
    psycopg2-binary==2.9.12 \
    requests==2.34.2 \
    python-dotenv==1.0.1

WORKDIR /opt/airflow/project

# Lets tasks import the repository package, for example ``from etl...``.
ENV PYTHONPATH=/opt/airflow/project
