import os
import re
from pathlib import Path

ENV_PATH = Path(".env")

KNOWN_TOKEN_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _write_env_lines(lines: list[str]) -> None:
    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def mask_token(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}...{value[-4:]}"


def list_tokens() -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    pattern = re.compile(r"^([A-Z0-9_]+)=(.*)$")

    for line in _read_env_lines():
        match = pattern.match(line.strip())
        if not match:
            continue

        key, raw_value = match.group(1), match.group(2).strip()
        if key not in KNOWN_TOKEN_KEYS or not raw_value:
            continue

        tokens.append({"key": key, "masked": mask_token(raw_value)})

    return tokens


def set_token(key: str, value: str) -> dict[str, str]:
    if key not in KNOWN_TOKEN_KEYS:
        raise ValueError(f"Token não suportado: {key}")

    lines = _read_env_lines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    replaced = False
    updated: list[str] = []

    for line in lines:
        if pattern.match(line.strip()):
            updated.append(f"{key}={value}")
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        updated.append(f"{key}={value}")

    _write_env_lines(updated)
    os.environ[key] = value
    return {"key": key, "masked": mask_token(value)}


def delete_token(key: str) -> bool:
    if key not in KNOWN_TOKEN_KEYS:
        raise ValueError(f"Token não suportado: {key}")

    lines = _read_env_lines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    kept = [line for line in lines if not pattern.match(line.strip())]

    if len(kept) == len(lines):
        return False

    _write_env_lines(kept)
    os.environ.pop(key, None)
    return True