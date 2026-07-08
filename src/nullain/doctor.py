from __future__ import annotations

import os
import re
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen

from nullain import memory
from nullain.env_tokens import ENV_PATH, KNOWN_TOKEN_KEYS
from nullain.mcp_client import CONFIG_PATH
from nullain.mcp_config_store import list_servers
from nullain.runtime import get_active_model

DEFAULT_PORT = 8420
_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def _env_key_present(key: str) -> bool:
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return True

    if not ENV_PATH.exists():
        return False

    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match and match.group(1).strip():
            return True
    return False


def _run_check(name: str, checker: Callable[[], CheckResult]) -> CheckResult:
    try:
        return checker()
    except Exception as exc:
        return CheckResult(name=name, ok=False, detail=str(exc), hint="Verifique o log acima.")


def _check_python() -> CheckResult:
    version = sys.version_info
    ok = version >= (3, 13)
    detail = f"{version.major}.{version.minor}.{version.micro}"
    hint = "Instale Python 3.13 ou superior." if not ok else ""
    return CheckResult("Python >= 3.13", ok, detail, hint)


def _check_env_file() -> CheckResult:
    exists = ENV_PATH.exists()
    return CheckResult(
        ".env existe",
        exists,
        "encontrado" if exists else "ausente",
        "Copie .env.example para .env e preencha as chaves necessárias." if not exists else "",
    )


def _check_token_key(key: str) -> CheckResult:
    present = _env_key_present(key)
    return CheckResult(
        f"Token {key}",
        present,
        "presente" if present else "ausente",
        "" if present else f"Defina {key} no .env se for usar esse provider.",
    )


def _check_active_model() -> CheckResult:
    try:
        model = get_active_model()
    except Exception:
        from nullain.config import get_settings

        model = get_settings().nullain_model
    return CheckResult("Modelo ativo", bool(model.strip()), model, "Defina NULLAIN_MODEL no .env.")


def _check_ollama() -> CheckResult:
    try:
        with urlopen(_OLLAMA_URL, timeout=2) as response:
            ok = 200 <= response.status < 300
    except (URLError, TimeoutError, OSError):
        ok = False

    return CheckResult(
        "Ollama local",
        ok,
        _OLLAMA_URL if ok else "sem resposta",
        "Instale e inicie o Ollama em http://127.0.0.1:11434." if not ok else "",
    )


def _check_piper_model() -> CheckResult:
    from nullain.voice.tts import resolve_piper_model_path

    path = resolve_piper_model_path()
    return CheckResult("Modelo Piper", True, str(path), "")


def _check_sqlite() -> CheckResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_path = Path(tmp_dir) / "doctor.db"
        original_path = memory.DB_PATH
        memory.DB_PATH = test_path
        try:
            memory.init_db()
            memory.set_setting("_doctor_probe", "ok")
            value = memory.get_setting("_doctor_probe")
            ok = value == "ok"
            detail = "leitura/escrita OK" if ok else "falha na leitura"
        finally:
            memory.DB_PATH = original_path

    return CheckResult(
        "Banco SQLite",
        ok,
        detail,
        "Verifique permissões de escrita no diretório do projeto." if not ok else "",
    )


def _check_mcp_config() -> CheckResult:
    if not CONFIG_PATH.exists():
        return CheckResult(
            "mcp.config.json",
            False,
            "ausente",
            "Copie mcp.config.example.json para mcp.config.json.",
        )

    servers = list_servers()
    names = [server.get("name", "?") for server in servers]
    detail = ", ".join(names) if names else "nenhum servidor"
    return CheckResult("mcp.config.json", True, detail, "")


def _check_port() -> CheckResult:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        in_use = sock.connect_ex(("127.0.0.1", DEFAULT_PORT)) == 0

    if in_use:
        return CheckResult(
            f"Porta {DEFAULT_PORT}",
            True,
            "em uso",
            "",
        )
    return CheckResult(
        f"Porta {DEFAULT_PORT}",
        True,
        "livre",
        "",
    )


def run_checks() -> list[CheckResult]:
    checks: list[CheckResult] = [
        _run_check("Python >= 3.13", _check_python),
        _run_check(".env existe", _check_env_file),
    ]

    for key in KNOWN_TOKEN_KEYS:
        checks.append(_run_check(f"Token {key}", lambda key=key: _check_token_key(key)))

    checks.extend(
        [
            _run_check("Modelo ativo", _check_active_model),
            _run_check("Ollama local", _check_ollama),
            _run_check("Modelo Piper", _check_piper_model),
            _run_check("Banco SQLite", _check_sqlite),
            _run_check("mcp.config.json", _check_mcp_config),
            _run_check(f"Porta {DEFAULT_PORT}", _check_port),
        ]
    )
    return checks


def format_doctor_report(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for result in results:
        mark = "✓" if result.ok else "✗"
        line = f"{mark} {result.name}: {result.detail}"
        if result.hint:
            line = f"{line} | {result.hint}"
        lines.append(line)

    ok_count = sum(1 for result in results if result.ok)
    lines.append(f"{ok_count}/{len(results)} checks OK")
    return "\n".join(lines)