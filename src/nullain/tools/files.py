from collections.abc import Callable
from pathlib import Path

ConfirmFn = Callable[[str], bool]

MAX_READ_CHARS = 10_000
PREVIEW_CHARS = 500


def list_files(path: str = ".") -> str:
    target = Path(path)

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
    target = Path(path)

    if not target.exists():
        return f"Erro: arquivo não existe: {path}"
    if not target.is_file():
        return f"Erro: não é um arquivo: {path}"

    content = target.read_text(encoding="utf-8")
    if len(content) > MAX_READ_CHARS:
        return content[:MAX_READ_CHARS] + "\n... (truncado)"

    return content


def write_file(path: str, content: str, confirm: ConfirmFn | None = None) -> str:
    target = Path(path)
    preview = (
        f"Caminho: {target}\n"
        f"Tamanho: {len(content)} caracteres\n\n"
        f"{content[:PREVIEW_CHARS]}"
    )
    if len(content) > PREVIEW_CHARS:
        preview += "\n... (preview truncado)"

    if confirm is not None and not confirm(preview):
        return "Operação cancelada pelo usuário."

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Arquivo gravado: {target}"