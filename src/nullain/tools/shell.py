import subprocess
from collections.abc import Callable

ConfirmFn = Callable[[str], bool]

MAX_OUTPUT_CHARS = 5000
TIMEOUT_SECONDS = 60


def run_command(cmd: str, confirm: ConfirmFn | None = None) -> str:
    if confirm is None:
        return (
            "Erro: esta operação exige confirmação, mas nenhum confirmador foi fornecido."
        )

    preview = f"Comando a executar:\n\n{cmd}"

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