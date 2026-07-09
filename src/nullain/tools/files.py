from collections.abc import Callable
from pathlib import Path

ConfirmFn = Callable[[str], bool]

MAX_READ_CHARS = 10_000
PREVIEW_CHARS = 500

# Espelhado por nullain.workspace.set_workspace_root(); testes monkeypatcham aqui.
WORKSPACE_ROOT = Path.cwd().resolve()


def _safe_path(path: str) -> Path:
    candidate = (WORKSPACE_ROOT / path).resolve()
    if candidate != WORKSPACE_ROOT and WORKSPACE_ROOT not in candidate.parents:
        raise ValueError(f"Caminho fora do workspace: {path}")
    return candidate


def list_files(path: str = ".") -> str:
    try:
        target = _safe_path(path)
    except ValueError as exc:
        return str(exc)

    if not target.exists():
        return f"Erro: caminho não existe: {path}"
    if not target.is_dir():
        return f"Erro: não é um diretório: {path}"

    entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
    if not entries:
        return "(diretório vazio)"

    lines: list[str] = []
    for entry in entries:
        label = "[DIR]" if entry.is_dir() else "[FILE]"
        lines.append(f"{label} {entry.name}")

    return "\n".join(lines)


def read_file(path: str) -> str:
    try:
        target = _safe_path(path)
    except ValueError as exc:
        return str(exc)

    if not target.exists():
        return f"Erro: arquivo não existe: {path}"
    if not target.is_file():
        return f"Erro: não é um arquivo: {path}"

    try:
        content = target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return f"Erro: não foi possível ler o arquivo como texto: {exc}"

    if len(content) > MAX_READ_CHARS:
        return content[:MAX_READ_CHARS] + "\n... (truncado)"

    return content


def write_file(path: str, content: str, confirm: ConfirmFn | None = None) -> str:
    if confirm is None:
        return (
            "Erro: esta operação exige confirmação, mas nenhum confirmador foi fornecido."
        )

    try:
        target = _safe_path(path)
    except ValueError as exc:
        return str(exc)

    preview = (
        f"Caminho: {target}\n"
        f"Tamanho: {len(content)} caracteres\n\n"
        f"{content[:PREVIEW_CHARS]}"
    )
    if len(content) > PREVIEW_CHARS:
        preview += "\n... (preview truncado)"

    if not confirm(preview):
        return "Operação cancelada pelo usuário."

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Arquivo gravado: {target}"
