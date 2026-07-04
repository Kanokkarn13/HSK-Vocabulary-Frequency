"""Transcribe HSK listening exam audio files using OpenAI Whisper (local)."""
import os
import whisper
from pathlib import Path

from etl.logging_config import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4"}


def load_model(model_size: str | None = None) -> whisper.Whisper:
    size = model_size or os.getenv("WHISPER_MODEL", "medium")
    logger.info("Loading Whisper model: %s", size)
    return whisper.load_model(size)


def transcribe_file(model: whisper.Whisper, audio_path: str | Path) -> str:
    result = model.transcribe(str(audio_path), language="zh")
    return result["text"]


def transcribe_all(
    input_dir: str | Path,
    model_size: str | None = None,
) -> dict[str, str]:
    """Return mapping of filename -> transcript for all audio files in dir."""
    model = load_model(model_size)
    results = {}
    for audio_file in Path(input_dir).iterdir():
        if audio_file.suffix.lower() not in SUPPORTED_EXTS:
            continue
        try:
            results[audio_file.name] = transcribe_file(model, audio_file)
            logger.info("Transcribed %s", audio_file.name)
        except Exception:
            logger.exception("Failed to transcribe %s", audio_file.name)
    return results
