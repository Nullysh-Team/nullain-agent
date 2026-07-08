from pathlib import Path

from nullain.config import get_settings


def resolve_piper_model_path() -> Path:
    settings = get_settings()

    if settings.nullain_piper_model_path:
        path = Path(settings.nullain_piper_model_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Modelo Piper não encontrado: {path}")

    voice_name = settings.nullain_piper_voice
    candidates = [
        Path.cwd() / f"{voice_name}.onnx",
        Path.home() / ".local" / "share" / "piper" / "voices" / f"{voice_name}.onnx",
        Path.home()
        / ".cache"
        / "redchan"
        / "models"
        / "tts"
        / f"vits-piper-{voice_name}"
        / f"{voice_name}.onnx",
        Path("models") / "piper" / f"{voice_name}.onnx",
        Path("models") / f"{voice_name}.onnx",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Modelo Piper não encontrado. Rode: "
        f"uv run python -m piper.download_voices {voice_name}"
    )