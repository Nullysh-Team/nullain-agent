from __future__ import annotations

import os
import re
import socket
import sqlite3
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
    mandatory: bool = True


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


def status_mark(result: CheckResult) -> str:
    if result.mandatory:
        return "✓" if result.ok else "✗"
    if result.detail == "—" or result.detail.startswith("inativa"):
        return "—"
    return "✓"


def score_summary(results: list[CheckResult]) -> tuple[int, int]:
    mandatory = [result for result in results if result.mandatory]
    ok_count = sum(1 for result in mandatory if result.ok)
    return ok_count, len(mandatory)


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
    if present:
        return CheckResult(f"Token {key}", True, "presente", mandatory=False)
    return CheckResult(
        f"Token {key}",
        True,
        "—",
        hint=f"Opcional: defina {key} no .env se for usar esse provider.",
        mandatory=False,
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
    from nullain.voice.paths import resolve_piper_model_path

    path = resolve_piper_model_path()
    return CheckResult("Modelo Piper", True, str(path), "")


def _check_sqlite() -> CheckResult:
    test_path: Path | None = None
    conn: sqlite3.Connection | None = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            test_path = Path(tmp_file.name)

        conn = sqlite3.connect(test_path)
        conn.execute("CREATE TABLE doctor_probe (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO doctor_probe (key, value) VALUES (?, ?)",
            ("probe", "ok"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM doctor_probe WHERE key = ?",
            ("probe",),
        ).fetchone()
        ok = row is not None and row[0] == "ok"
        detail = "leitura/escrita OK" if ok else "falha na leitura"
        hint = "" if ok else "Verifique permissões de escrita no diretório temporário."
        return CheckResult("Banco SQLite", ok, detail, hint)
    except Exception as exc:
        return CheckResult(
            "Banco SQLite",
            False,
            str(exc),
            "Verifique permissões de escrita no diretório temporário.",
        )
    finally:
        if conn is not None:
            conn.close()
        if test_path is not None:
            test_path.unlink(missing_ok=True)


def _check_semantic_search() -> CheckResult:
    from nullain.config import get_settings

    model = get_settings().nullain_embed_model.strip()
    if not model:
        return CheckResult(
            "Busca semântica",
            True,
            "inativa: modelo de embedding não configurado",
            mandatory=False,
        )

    if not memory.VEC_AVAILABLE:
        return CheckResult(
            "Busca semântica",
            True,
            "inativa: sqlite-vec indisponível",
            mandatory=False,
        )

    facts = memory.list_facts()
    pending = [fact for fact in facts if not memory.fact_has_embedding(fact.id)]
    if facts and pending:
        return CheckResult(
            "Busca semântica",
            True,
            f"inativa: {len(pending)} embeddings pendentes",
            hint="Inicie o Ollama para o backfill automático.",
            mandatory=False,
        )

    return CheckResult(
        "Busca semântica",
        True,
        f"ativa (sqlite-vec + {model})",
        mandatory=False,
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


def _check_latency_metrics() -> CheckResult:
    try:
        percentiles = memory.get_metric_percentiles("ttft_ms", limit=100)
    except Exception:
        return CheckResult("Métricas de latência", True, "—", mandatory=False)

    count = percentiles.get("count", 0)
    if count == 0:
        return CheckResult(
            "Métricas de latência",
            True,
            "sem dados (nenhum turno medido ainda)",
            mandatory=False,
        )

    p50 = percentiles.get("p50")
    p95 = percentiles.get("p95")
    detail = f"TTFT p50={p50:.0f}ms p95={p95:.0f}ms ({count} turnos)" if p50 and p95 else f"{count} turnos"
    return CheckResult("Métricas de latência", True, detail, mandatory=False)


def _check_workspace() -> CheckResult:
    from nullain.workspace import resolve_workspace_root

    root = resolve_workspace_root()
    # Não muta o processo do doctor; só reporta o path efetivo.
    exists = root.exists() and root.is_dir()
    detail = str(root)
    hint = "" if exists else "Crie o diretório ou ajuste NULLAIN_WORKSPACE."
    return CheckResult("Workspace", exists, detail, hint)


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
            _run_check("Busca semântica", _check_semantic_search),
            _run_check("Workspace", _check_workspace),
            _run_check("mcp.config.json", _check_mcp_config),
            _run_check(f"Porta {DEFAULT_PORT}", _check_port),
            _run_check("Métricas de latência", _check_latency_metrics),
        ]
    )
    return checks


def format_doctor_report(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for result in results:
        mark = status_mark(result)
        line = f"{mark} {result.name}: {result.detail}"
        if result.hint:
            line = f"{line} | {result.hint}"
        lines.append(line)

    ok_count, total = score_summary(results)
    lines.append(f"{ok_count}/{total} checks OK")
    return "\n".join(lines)