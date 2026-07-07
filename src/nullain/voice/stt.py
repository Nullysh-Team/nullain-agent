from functools import lru_cache
from pathlib import Path

from nullain.config import get_settings


@lru_cache
def _get_model():
    from faster_whisper import WhisperModel

    settings = get_settings()
    return WhisperModel(
        settings.nullain_whisper_model,
        device=settings.nullain_whisper_device,
        compute_type=settings.nullain_whisper_compute_type,
    )


def transcribe_file(path: str | Path) -> str:
    model = _get_model()
    segments, _info = model.transcribe(
        str(path),
        language="pt",
        vad_filter=True,
    )
    parts = [segment.text.strip() for segment in segments if segment.text.strip()]
    return " ".join(parts).strip()