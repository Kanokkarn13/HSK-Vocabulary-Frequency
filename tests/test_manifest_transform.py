from pathlib import Path

import pandas as pd
import json

from etl.manifest import build_raw_snapshot, run_extraction
from etl.transform_batch import clean_text, transform_raw


def test_manifest_reuses_unchanged_source_across_batches(tmp_path: Path):
    reading = tmp_path / "reading"
    listening = tmp_path / "listening"
    reading.mkdir()
    listening.mkdir()
    source = listening / "HSK3_2020.mp3"
    source.write_bytes(b"audio fixture")
    manifest = tmp_path / "manifest.json"

    calls = []

    def transcriber(path):
        calls.append(path)
        return "你好。"

    first = run_extraction(
        batch_id="batch-1",
        reading_dir=reading,
        listening_dir=listening,
        staging_root=tmp_path / "staging",
        manifest_path=manifest,
        transcriber_factory=lambda: transcriber,
        require_sources=True,
    )
    second = run_extraction(
        batch_id="batch-2",
        reading_dir=reading,
        listening_dir=listening,
        staging_root=tmp_path / "staging",
        manifest_path=manifest,
        transcriber_factory=lambda: (_ for _ in ()).throw(AssertionError("should reuse")),
        require_sources=True,
    )

    assert first["status"] == "updated"
    assert second["status"] == "updated"
    assert len(calls) == 1
    assert second["row_count"] == 1


def test_manifest_quarantines_failed_source_without_advancing_manifest(tmp_path: Path):
    reading = tmp_path / "reading"
    listening = tmp_path / "listening"
    reading.mkdir()
    listening.mkdir()
    source = listening / "HSK3_2020.mp3"
    source.write_bytes(b"audio fixture")
    manifest = tmp_path / "manifest.json"

    try:
        run_extraction(
            batch_id="batch-failed",
            reading_dir=reading,
            listening_dir=listening,
            staging_root=tmp_path / "staging",
            manifest_path=manifest,
            transcriber_factory=lambda: (_ for _ in ()).throw(RuntimeError("timeout")),
            require_sources=True,
        )
    except ValueError as exc:
        assert "Extraction failed" in str(exc)
    else:
        raise AssertionError("failed source must fail the batch")

    assert not manifest.exists()
    assert list((tmp_path / "staging" / "batch-failed" / "quarantine").rglob("*.mp3"))


def test_build_raw_snapshot_merges_manifest_text_artifacts(tmp_path: Path):
    text_path = tmp_path / "source.txt"
    text_path.write_text("你好。", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_key": "reading:x.pdf",
                        "exam_id": "x",
                        "hsk_level": 3,
                        "source_type": "reading",
                        "filename": "x.pdf",
                        "text_path": text_path.as_posix(),
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_raw_snapshot(manifest, tmp_path / "raw.parquet")

    assert result["row_count"] == 1
    assert pd.read_parquet(tmp_path / "raw.parquet").iloc[0]["text"] == "你好。"


def test_transform_uses_shared_tokenizer_and_writes_quality_report(tmp_path: Path):
    raw_path = tmp_path / "raw.parquet"
    wordlist_path = tmp_path / "words.csv"
    raw = pd.DataFrame(
        [
            {"exam_id": "2020-01", "hsk_level": 3, "source_type": "reading", "filename": "x.pdf", "text": "你好世界。"},
        ]
    )
    raw.to_parquet(raw_path, index=False)
    pd.DataFrame(
        [
            {"word": "你好", "level": 1},
            {"word": "世界", "level": 1},
        ]
    ).to_csv(wordlist_path, index=False)

    result = transform_raw(raw_path, wordlist_path, tmp_path / "out")
    assert result["status"] == "updated"
    assert result["match_rate"] >= 0.0
    assert Path(result["counts_path"]).exists()
    assert Path(result["quality_report_path"]).exists()


def test_clean_text_collapses_listening_repetition():
    assert clean_text("大家好啊大家好啊大家好啊。", "listening").count("大家好啊") == 1
