"""Garante que mktemp não é mais usado nos caminhos de voz/API."""

from pathlib import Path


def test_server_voice_transcribe_does_not_use_mktemp():
    source = Path("src/nullain/server.py").read_text(encoding="utf-8")
    assert "mktemp" not in source
    assert "mkstemp" in source


def test_voice_audio_does_not_use_mktemp():
    source = Path("src/nullain/voice/audio.py").read_text(encoding="utf-8")
    assert "mktemp" not in source
    assert "mkstemp" in source
