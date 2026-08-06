"""Incremental source inventory and extraction for the Airflow batch pipeline."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from etl.logging_config import get_logger


LOGGER = get_logger(__name__)
SUPPORTED = {
    "reading": {".pdf"},
    "listening": {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4"},
}


def parse_filename_metadata(filename: str) -> tuple[int | None, int | None]:
    year_match = re.search(r"(20\d{2})", filename)
    level_match = re.search(r"[Hh][Ss][Kk](\d)", filename)
    return (
        int(year_match.group(1)) if year_match else None,
        int(level_match.group(1)) if level_match else None,
    )


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".json", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return {}
    with open(candidate, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Manifest must contain a JSON object: {candidate}")
    return payload


def inventory_sources(reading_dir: str | Path, listening_dir: str | Path) -> list[dict[str, Any]]:
    """Return deterministic file metadata for supported reading/listening inputs."""

    records: list[dict[str, Any]] = []
    for source_type, root_value in (("reading", reading_dir), ("listening", listening_dir)):
        root = Path(root_value)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED[source_type]:
                continue
            relative = path.relative_to(root).as_posix()
            year, hsk_level = parse_filename_metadata(path.name)
            exam_match = path.stem
            if exam_match.lower().startswith("hsk"):
                exam_match = exam_match.split(" ", 1)[0].split("-", 1)[0]
            records.append(
                {
                    "source_key": f"{source_type}:{relative}",
                    "source_type": source_type,
                    "relative_path": relative,
                    "filename": path.name,
                    "absolute_path": str(path.resolve()),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "year": year,
                    "hsk_level": hsk_level,
                    "exam_id": exam_match,
                    "file_type": path.suffix.lower().lstrip("."),
                }
            )
    return records


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _quarantine(path: Path, quarantine_dir: Path, batch_id: str) -> str:
    destination = quarantine_dir / batch_id / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return str(destination)


def _validate_raw(frame: pd.DataFrame, *, require_sources: bool = True) -> dict[str, Any]:
    required = {"exam_id", "hsk_level", "source_type", "filename", "text"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Raw extraction is missing columns: {sorted(missing)}")
    if frame.empty and require_sources:
        raise ValueError("Raw extraction contains no sources")
    duplicate = frame.duplicated(["exam_id", "source_type"], keep=False)
    if duplicate.any():
        raise ValueError("Raw extraction contains duplicate (exam_id, source_type) keys")
    empty = frame["text"].fillna("").astype(str).str.strip().eq("")
    if empty.any():
        raise ValueError(f"Raw extraction contains {int(empty.sum())} empty texts")
    return {"row_count": int(len(frame)), "source_types": sorted(frame["source_type"].unique().tolist())}


def _extract_source_text(
    source: dict[str, Any],
    previous_by_key: dict[str, dict[str, Any]],
    checkpoint_sources: dict[str, dict[str, Any]],
    text_root: Path,
    transcriber: Any,
    *,
    transcriber_factory: Callable[[], Any] | None,
) -> tuple[dict[str, Any], Any]:
    """Extract or reuse one source and return its manifest row."""

    previous_row = previous_by_key.get(source["source_key"], {})
    checkpoint_row = checkpoint_sources.get(source["source_key"], {})
    text_path_value = checkpoint_row.get("text_path") or previous_row.get("text_path")
    text_path = Path(text_path_value) if text_path_value else None
    unchanged = previous_row.get("sha256") == source["sha256"] and text_path is not None and text_path.exists()
    if unchanged:
        text = text_path.read_text(encoding="utf-8")
        status = "reused"
    else:
        text, transcriber = _extract_new_source(source, transcriber, transcriber_factory)
        if not str(text).strip():
            raise ValueError("extraction returned empty text")
        text_path = text_root / source["source_type"] / f"{source['sha256']}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(str(text), encoding="utf-8")
        status = "extracted"

    enriched = {
        **source,
        "status": status,
        "text_path": str(text_path),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_length": len(text),
        "text": text,
    }
    return enriched, transcriber


def _extract_new_source(
    source: dict[str, Any],
    transcriber: Any,
    transcriber_factory: Callable[[], Any] | None,
) -> tuple[str, Any]:
    source_path = Path(source["absolute_path"])
    if source["source_type"] == "reading":
        from etl.extract_pdf import extract_text_from_pdf

        return extract_text_from_pdf(source_path), transcriber

    if transcriber is None:
        if transcriber_factory is not None:
            transcriber = transcriber_factory()
        else:
            from etl.transcribe_audio import load_model, transcribe_file

            transcriber = (load_model(), transcribe_file)
    if isinstance(transcriber, tuple):
        return transcriber[1](transcriber[0], source_path), transcriber
    return transcriber(source_path), transcriber


def _reuse_existing_snapshot(
    stage: Path,
    existing_raw_path: str | Path | None,
    require_sources: bool,
    batch_id: str,
) -> dict[str, Any] | None:
    if require_sources or not existing_raw_path:
        return None
    raw_path = Path(existing_raw_path)
    if not raw_path.exists():
        return None
    frame = pd.read_parquet(raw_path)
    quality = _validate_raw(frame, require_sources=True)
    _atomic_parquet(frame, stage / "raw_extractions.parquet")
    return {
        "status": "skipped",
        "reason": "no_source_files",
        "changed_source_count": 0,
        "reused_source_count": 0,
        **quality,
        "batch_id": batch_id,
    }


def run_extraction(
    *,
    batch_id: str,
    reading_dir: str | Path,
    listening_dir: str | Path,
    staging_root: str | Path,
    manifest_path: str | Path,
    existing_raw_path: str | Path | None = None,
    require_sources: bool = False,
    transcriber_factory: Callable[[], Any] | None = None,
    source_types: set[str] | None = None,
) -> dict[str, Any]:
    """Extract only changed source files and build a staged raw snapshot.

    The checkpoint is updated after each successful file. A failed source is
    copied to quarantine and the batch fails before the persistent manifest is
    advanced, keeping the last successful inventory reusable.
    """

    stage = Path(staging_root) / batch_id
    text_root = stage / "source_text"
    checkpoint_path = stage / "checkpoint.json"
    stage_manifest_path = stage / "manifest.json"
    stage.mkdir(parents=True, exist_ok=True)
    previous = load_json(manifest_path)
    previous_by_key = {row["source_key"]: row for row in previous.get("sources", [])}
    checkpoint = load_json(checkpoint_path)
    checkpoint_sources = checkpoint.get("sources", {})

    inventory = inventory_sources(reading_dir, listening_dir)
    if source_types is not None:
        inventory = [source for source in inventory if source["source_type"] in source_types]
    if not inventory:
        reused = _reuse_existing_snapshot(stage, existing_raw_path, require_sources, batch_id)
        if reused is not None:
            return reused
        raise FileNotFoundError("No supported PDF/audio source files were found")

    transcriber = None
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    changed_source_count = 0
    reused_source_count = 0
    for source in inventory:
        try:
            enriched, transcriber = _extract_source_text(
                source,
                previous_by_key,
                checkpoint_sources,
                text_root,
                transcriber,
                transcriber_factory=transcriber_factory,
            )
            rows.append(enriched)
            if enriched["status"] == "extracted":
                changed_source_count += 1
            else:
                reused_source_count += 1
            checkpoint_sources[source["source_key"]] = {key: value for key, value in enriched.items() if key != "text"}
            _atomic_json(checkpoint_path, {"batch_id": batch_id, "sources": checkpoint_sources})
        except Exception as exc:  # noqa: BLE001 - preserve all source errors in the report
            quarantine_path = _quarantine(Path(source["absolute_path"]), stage / "quarantine", batch_id)
            error = {**source, "status": "quarantined", "error": str(exc), "quarantine_path": quarantine_path}
            errors.append(error)
            LOGGER.exception("Failed to extract %s", source["absolute_path"])

    if errors:
        _atomic_json(stage_manifest_path, {"batch_id": batch_id, "sources": rows + errors, "errors": errors})
        raise ValueError(f"Extraction failed for {len(errors)} source files; see {stage_manifest_path}")

    frame = pd.DataFrame(rows)
    quality = _validate_raw(frame, require_sources=True)
    _atomic_parquet(frame, stage / "raw_extractions.parquet")
    # Preserve the other source type when PDF and audio run as separate tasks,
    # but do not preserve deleted/moved files from the source type processed by
    # this task.  Keeping missing rows here would make a deleted source remain
    # in every future raw snapshot and production publish.
    processed_types = source_types or {"reading", "listening"}
    current_source_keys = {source["source_key"] for source in inventory}
    merged_sources = {
        row["source_key"]: row
        for row in previous.get("sources", [])
        if row.get("source_type") not in processed_types
        or row.get("source_key") in current_source_keys
    }
    merged_sources.update(
        {
            row["source_key"]: {key: value for key, value in row.items() if key != "text"}
            for row in rows
        }
    )
    manifest = {
        "schema_version": 1,
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": list(merged_sources.values()),
        "quality": quality,
    }
    _atomic_json(stage_manifest_path, manifest)
    _atomic_json(Path(manifest_path), manifest)
    return {
        "status": "updated",
        "batch_id": batch_id,
        "changed_source_count": changed_source_count,
        "reused_source_count": reused_source_count,
        **quality,
        "manifest_path": str(stage_manifest_path),
    }


def build_raw_snapshot(manifest_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Rebuild a complete raw snapshot from the persistent source manifest."""

    manifest = load_json(manifest_path)
    rows = []
    for source in manifest.get("sources", []):
        text_path = Path(source.get("text_path", ""))
        if not text_path.exists():
            raise FileNotFoundError(f"Manifest text artifact is missing: {text_path}")
        rows.append({**source, "text": text_path.read_text(encoding="utf-8")})
    frame = pd.DataFrame(rows)
    quality = _validate_raw(frame, require_sources=True)
    _atomic_parquet(frame, Path(output_path))
    return {"status": "updated", "raw_path": str(output_path), **quality}


__all__ = ["build_raw_snapshot", "inventory_sources", "run_extraction", "sha256_file"]
