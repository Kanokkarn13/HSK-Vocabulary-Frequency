from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_airflow_compose_fails_closed_for_production_inputs_and_publish():
    compose = (ROOT / "airflow" / "config" / "docker-compose.airflow.yml").read_text(encoding="utf-8")
    assert "HSK_REQUIRE_SOURCE_FILES:-true" in compose
    assert "HSK_WORDLIST_REQUIRE_API:-true" in compose
    assert "HSK_PUBLISH_ENABLED:-false" in compose


def test_airflow_dag_declares_bangkok_timezone_and_publish_gate():
    dag = (ROOT / "airflow" / "dags" / "hsk_batch_pipeline.py").read_text(encoding="utf-8")
    assert 'tz="Asia/Bangkok"' in dag
    assert "publish_enabled()" in dag
