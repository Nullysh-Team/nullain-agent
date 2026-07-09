import subprocess
from collections.abc import Callable
from pathlib import Path

from nullain.tools import files
from nullain.tools.sandbox import DEFAULT_DENY_PATTERNS, evaluate_command

ConfirmFn = Callable[[str], bool]

MAX_OUTPUT_CHARS = 5000
TIMEOUT_SECONDS = 60


def _workspace_cwd() -> Path:
    return Path(files.WORKSPACE_ROOT).resolve()


def _sandbox_config() -> tuple[bool, list[str] | None, list[str]]:
    try:
        from nullain.config import get_settings

        settings = get_settings()
        enabled = bool(settings.nullain_shell_sandbox)
        raw_allow = (settings.nullain_shell_allowlist or "").strip()
        allowlist = [item.strip() for item in raw_allow.split(",") if item.strip()] or None
        raw_extra = (settings.nullain_shell_deny_extra or "").strip()
        extra_deny = [item.strip() for item in raw_extra.split("||") if item.strip()]
        return enabled, allowlist, extra_deny
    except Exception:
        return True, None, []


def run_command(cmd: str, confirm: ConfirmFn | None = None) -> str:
    if confirm is None:
        return (
            "Erro: esta operação exige confirmação, mas nenhum confirmador foi fornecido."
        )

    cwd = _workspace_cwd()
    enabled, allowlist, extra_deny = _sandbox_config()
    deny = list(DEFAULT_DENY_PATTERNS) + extra_deny
    decision = evaluate_command(
        cmd,
        deny_patterns=deny,
        allowlist=allowlist,
        enabled=enabled,
    )
    if not decision.allowed:
        return f"Erro: sandbox bloqueou o comando — {decision.reason}"

    sandbox_note = "sandbox=on" if enabled else "sandbox=off"
    preview = f"Comando a executar (cwd={cwd}, {sandbox_note}):\n\n{cmd}"

    if not confirm(preview):
        return "Operação cancelada pelo usuário."

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
        )
    except subprocess.TimeoutExpired:
        return f"Erro: comando excedeu o timeout de {TIMEOUT_SECONDS}s."
    except Exception as exc:
        return f"Erro ao executar comando: {exc}"

    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout)
    if result.stderr:
        parts.append(result.stderr)

    output = "\n".join(parts).strip()
    if not output:
        output = f"(comando finalizou com código {result.returncode}, sem saída)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncado)"

    return output
