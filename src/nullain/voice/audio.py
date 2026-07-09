import io
import os
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from nullain.config import get_settings

SAMPLE_RATE = 16_000


def record_seconds(seconds: float | None = None) -> str:
    settings = get_settings()
    duration = seconds or settings.nullain_voice_record_seconds

    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()

    fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(temp_path, audio, SAMPLE_RATE)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return temp_path


def play_wav_bytes(data: bytes) -> None:
    if not data:
        return

    with io.BytesIO(data) as buffer:
        audio, sample_rate = sf.read(buffer, dtype="float32")

    if isinstance(audio, np.ndarray) and audio.size == 0:
        return

    sd.play(audio, sample_rate)
    sd.wait()