import io
import wave
from functools import lru_cache

from nullain.voice.paths import resolve_piper_model_path


@lru_cache
def _get_voice():
    from piper import PiperVoice

    return PiperVoice.load(str(resolve_piper_model_path()))


def synthesize_wav_bytes(text: str) -> bytes:
    if not text.strip():
        return b""

    voice = _get_voice()
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    return buffer.getvalue()