"""Full incremental ETL DAG for HSK vocabulary frequency data."""

from __future__ import annotations

import logging
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.sdk import dag, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException, AirflowSkipException


PROJECT_DIR = Path("/opt/airflow/project")
DATA_DIR = PROJECT_DIR / "data"
LOGGER = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _batch_id() -> str:
    context = get_current_context()
    run_id = str(context["dag_run"].run_id)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id)[:180]


def _failure_callback(context: dict[str, Any]) -> None:
    task_instance = context.get("task_instance")
    LOGGER.error(
        "HSK ETL task failed dag_id=%s task_id=%s run_id=%s",
        getattr(task_instance, "dag_id", "unknown"),
        getattr(task_instance, "task_id", "unknown"),
        context.get("run_id", "unknown"),
    )
    webhook = os.getenv("HSK_ALERT_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            import requests

            requests.post(
                webhook,
                json={
                    "text": "HSK ETL failed",
                    "dag_id": getattr(task_instance, "dag_id", "unknown"),
                    "task_id": getattr(task_instance, "task_id", "unknown"),
                    "run_id": context.get("run_id", "unknown"),
                },
                timeout=10,
            ).raise_for_status()
        except Exception:  # noqa: BLE001 - notification must not mask the failure
            LOGGER.exception("Could not send HSK_ALERT_WEBHOOK_URL notification")


def _retry_callback(context: dict[str, Any]) -> None:
    task_instance = context.get("task_instance")
    LOGGER.warning(
        "HSK ETL task retry dag_id=%s task_id=%s try=%s/%s",
        getattr(task_instance, "dag_id", "unknown"),
        getattr(task_instance, "task_id", "unknown"),
        getattr(task_instance, "try_number", "?"),
        getattr(task_instance, "max_tries", "?"),
    )


SCHEDULE = "0 2 * * 1" if _env_bool("HSK_AIRFLOW_ENABLE_SCHEDULE") else None


@dag(
    dag_id="hsk_batch_pipeline",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=3,
    dagrun_timeout=timedelta(hours=8),
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=30),
        "on_failure_callback": _failure_callback,
        "on_retry_callback": _retry_callback,
    },
    tags=["hsk", "etl", "incremental", "learning"],
)
def hsk_batch_pipeline():
    @task(execution_timeout=timedelta(minutes=15), pool="hsk_api_pool")
    def refresh_wordlist_if_changed() -> dict[str, object]:
        from datetime import timedelta
        import requests

        from etl.extract_wordlist import run

        try:
            return run(
                output_dir=DATA_DIR / "processed",
                force=_env_bool("HSK_WORDLIST_FORCE_REFRESH"),
                require_api=_env_bool("HSK_WORDLIST_REQUIRE_API"),
                max_age=timedelta(hours=float(os.getenv("HSK_WORDLIST_MAX_AGE_HOURS", "168"))),
            )
        except (requests.Timeout, requests.ConnectionError):
            # Let Airflow retry network failures using the DAG retry policy.
            raise
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {408, 425, 429} or status is not None and status >= 500:
                raise
            raise AirflowFailException(f"Wordlist API permanent HTTP error: {exc}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise AirflowFailException(f"Wordlist input failed validation: {exc}") from exc

    @task(execution_timeout=timedelta(minutes=15))
    def inventory_sources(_wordlist_state: dict[str, object]) -> dict[str, object]:
        from etl.manifest import inventory_sources as build_inventory

        records = build_inventory(DATA_DIR / "reading", DATA_DIR / "listening")
        return {"source_count": len(records), "source_types": sorted({row["source_type"] for row in records})}

    def _extract_source_type(source_type: str, _inventory_state: dict[str, object]) -> dict[str, object]:
        from etl.manifest import run_extraction

        batch_id = _batch_id()
        result = run_extraction(
            batch_id=batch_id,
            reading_dir=DATA_DIR / "reading",
            listening_dir=DATA_DIR / "listening",
            staging_root=DATA_DIR / "staging",
            manifest_path=DATA_DIR / "raw" / "extraction_manifest.json",
            existing_raw_path=DATA_DIR / "raw" / "raw_extractions.parquet",
            require_sources=_env_bool("HSK_REQUIRE_SOURCE_FILES"),
            source_types={source_type},
        )
        return {**result, "raw_path": str(DATA_DIR / "staging" / batch_id / "raw_extractions.parquet")}

    @task(execution_timeout=timedelta(hours=2))
    def extract_pdfs(inventory_state: dict[str, object]) -> dict[str, object]:
        return _extract_source_type("reading", inventory_state)

    @task(execution_timeout=timedelta(hours=6), pool="hsk_whisper_pool")
    def transcribe_audio(inventory_state: dict[str, object]) -> dict[str, object]:
        return _extract_source_type("listening", inventory_state)

    @task(execution_timeout=timedelta(minutes=5))
    def should_process_batch(
        wordlist_state: dict[str, object],
        pdf_state: dict[str, object],
        audio_state: dict[str, object],
    ) -> bool:
        from sqlalchemy import text

        from etl.batch_gate import should_process_batch as decide
        from etl.load_to_db import get_engine

        force = _env_bool("HSK_FORCE_FULL_RUN")
        engine = get_engine()
        try:
            with engine.connect() as connection:
                production_exists = (
                    connection.execute(
                        text("SELECT EXISTS (SELECT 1 FROM etl_publish_state WHERE state_key = 'production')")
                    ).scalar_one()
                    if connection.execute(
                        text(
                            "SELECT to_regclass('public.etl_publish_state') IS NOT NULL"
                        )
                    ).scalar_one()
                    else False
                )
        finally:
            engine.dispose()

        process = decide(
            wordlist_changed=bool(wordlist_state.get("changed", False)),
            extraction_states=[pdf_state, audio_state],
            production_exists=bool(production_exists),
            force=force,
        )
        if not process:
            LOGGER.info("No changed wordlist/source detected; skipping transform and publish")
            raise AirflowSkipException("No changes since the last successful production batch")
        return True

    @task(execution_timeout=timedelta(minutes=15))
    def build_raw_snapshot(
        pdf_state: dict[str, object], audio_state: dict[str, object]
    ) -> dict[str, object]:
        from etl.manifest import build_raw_snapshot as assemble_raw

        batch_id = str(pdf_state.get("batch_id") or audio_state.get("batch_id") or _batch_id())
        output = DATA_DIR / "staging" / batch_id / "raw_extractions.parquet"
        if (DATA_DIR / "raw" / "extraction_manifest.json").exists():
            return assemble_raw(DATA_DIR / "raw" / "extraction_manifest.json", output)
        # No source files in a development checkout: retain the known-good raw snapshot.
        result = run_fallback_raw_snapshot(output)
        return {**result, "batch_id": batch_id}

    def run_fallback_raw_snapshot(output: Path) -> dict[str, object]:
        import pandas as pd

        raw = pd.read_parquet(DATA_DIR / "raw" / "raw_extractions.parquet")
        output.parent.mkdir(parents=True, exist_ok=True)
        raw.to_parquet(output, index=False)
        return {"status": "skipped", "reason": "manifest_not_available", "raw_path": str(output), "row_count": len(raw)}

    @task(execution_timeout=timedelta(hours=2))
    def transform_counts(
        extraction_state: dict[str, object],
        _wordlist_state: dict[str, object],
    ) -> dict[str, object]:
        from etl.transform_batch import transform_raw

        batch_id = str(extraction_state["batch_id"])
        output_dir = DATA_DIR / "staging" / batch_id
        report = transform_raw(
            extraction_state["raw_path"],
            DATA_DIR / "processed" / "hsk_wordlist.csv",
            output_dir,
            quality_report_path=output_dir / "transform_quality_report.json",
        )
        # The checked-in Jieba benchmark's best reviewed mode is ~0.855;
        # production must not silently regress below that baseline.  Teams can
        # raise this after a new benchmark is approved.
        min_rate = float(os.getenv("HSK_MIN_MATCH_RATE", "0.85"))
        if float(report["match_rate"]) < min_rate:
            raise ValueError(
                f"Transform match rate {report['match_rate']} is below configured minimum {min_rate}"
            )
        max_level_one = os.getenv("HSK_MAX_LEVEL1_SHARE", "").strip()
        if max_level_one and float(report["hsk1_occurrence_share"]) > float(max_level_one):
            raise ValueError(
                f"HSK 1 occurrence share {report['hsk1_occurrence_share']} exceeds configured maximum {max_level_one}"
            )
        baseline_path = os.getenv("HSK_TRANSFORM_BASELINE_PATH", "").strip()
        if baseline_path:
            baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
            allowed_drop = float(os.getenv("HSK_MATCH_RATE_BASELINE_TOLERANCE", "0.01"))
            baseline_rate = float(baseline["match_rate"])
            if float(report["match_rate"]) < baseline_rate - allowed_drop:
                raise ValueError(
                    f"Transform match rate {report['match_rate']} regressed from baseline {baseline_rate}"
                )
        return report

    @task(execution_timeout=timedelta(minutes=45), pool="hsk_db_write_pool")
    def stage_database(
        extraction_state: dict[str, object],
        transform_state: dict[str, object],
    ) -> dict[str, object]:
        from etl.stage_database import stage_batch

        batch_id = str(extraction_state["batch_id"])
        return stage_batch(
            batch_id=batch_id,
            wordlist_path=DATA_DIR / "processed" / "hsk_wordlist.csv",
            raw_path=extraction_state["raw_path"],
            counts_path=transform_state["counts_path"],
        )

    @task(execution_timeout=timedelta(minutes=10), pool="hsk_db_write_pool")
    def publish_database(stage_state: dict[str, object]) -> dict[str, object]:
        from etl.publish_gate import publish_enabled

        batch_id = str(stage_state["batch_id"])
        if not publish_enabled():
            LOGGER.warning(
                "Production publish is disabled (HSK_PUBLISH_ENABLED is not true); "
                "staged batch %s will be retained without replacing production",
                batch_id,
            )
            return {
                "status": "skipped",
                "reason": "HSK_PUBLISH_ENABLED=false",
                "batch_id": batch_id,
                "staging_counts": stage_state.get("staging_counts", {}),
            }

        from etl.stage_database import publish_batch

        return publish_batch(batch_id)

    @task(execution_timeout=timedelta(minutes=15))
    def validate_database(publish_state: dict[str, object]) -> dict[str, object]:
        if publish_state.get("status") == "skipped":
            LOGGER.info("Production validation skipped because publish was disabled")
            return {
                "status": "skipped",
                "reason": publish_state.get("reason", "publish_disabled"),
                "batch_id": publish_state.get("batch_id"),
            }

        from sqlalchemy import text

        from etl.load_to_db import get_engine

        tables = [
            "hsk_wordlist",
            "exam_sources",
            "word_frequencies",
            "frequency_aggregates",
            "exam_sentences",
        ]
        engine = get_engine()
        try:
            with engine.connect() as connection:
                counts = {}
                for table in tables:
                    counts[table] = int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
                    if counts[table] == 0:
                        raise ValueError(f"Production quality check failed: {table} is empty")
                expected = publish_state.get("production_counts", {})
                if expected and counts != expected:
                    raise ValueError(f"Production counts changed during validation: expected={expected}, actual={counts}")
                state = connection.execute(
                    text("SELECT batch_id FROM etl_publish_state WHERE state_key = 'production'")
                ).scalar_one_or_none()
                if state != publish_state.get("batch_id"):
                    raise ValueError(
                        f"Production publish state mismatch: expected={publish_state.get('batch_id')}, actual={state}"
                    )
                LOGGER.info("Production validation passed: %s", counts)
                return {"status": "success", "counts": counts}
        finally:
            engine.dispose()

    @task(execution_timeout=timedelta(minutes=5))
    def api_smoke_test(_database_state: dict[str, object]) -> dict[str, str]:
        if _database_state.get("status") == "skipped":
            return {"status": "skipped", "reason": "publish_disabled"}

        smoke_url = os.getenv("HSK_API_SMOKE_URL", "").strip()
        if not smoke_url:
            LOGGER.info("HSK_API_SMOKE_URL is not configured; API smoke test skipped")
            return {"status": "skipped", "reason": "HSK_API_SMOKE_URL_not_configured"}
        import requests

        response = requests.get(smoke_url, timeout=20)
        response.raise_for_status()
        return {"status": "success", "url": smoke_url}

    wordlist = refresh_wordlist_if_changed()
    inventory = inventory_sources(wordlist)
    pdf_state = extract_pdfs(inventory)
    audio_state = transcribe_audio(inventory)
    # Both extractors update the shared persistent manifest.  Serialize them
    # to avoid a last-writer-wins race when both source types change together.
    pdf_state >> audio_state
    process_gate = should_process_batch(wordlist, pdf_state, audio_state)
    extraction = build_raw_snapshot(pdf_state, audio_state)
    process_gate >> extraction
    transformed = transform_counts(extraction, wordlist)
    process_gate >> transformed
    staged = stage_database(extraction, transformed)
    published = publish_database(staged)
    validated = validate_database(published)
    api_smoke_test(validated)


hsk_batch_pipeline()
