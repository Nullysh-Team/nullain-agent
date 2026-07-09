"""Workspace root fixo para jail de arquivos e shell."""

from __future__ import annotations

from pathlib import Path

# Valor efetivo usado por tools. Testes podem monkeypatchar este símbolo
# ou chamar set_workspace_root().
WORKSPACE_ROOT = Path.cwd().resolve()


def resolve_workspace_root(raw: str | None = None) -> Path:
    """Resolve path do workspace a partir de config ou string explícita."""
    if raw is None:
        from nullain.config import get_settings

        raw = (get_settings().nullain_workspace or "").strip()
    else:
        raw = raw.strip()

    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def set_workspace_root(path: Path | str | None = None) -> Path:
    """Atualiza WORKSPACE_ROOT (e espelha em tools.files para compat)."""
    global WORKSPACE_ROOT

    if path is None:
        WORKSPACE_ROOT = resolve_workspace_root()
    else:
        WORKSPACE_ROOT = Path(path).expanduser().resolve()

    try:
        from nullain.tools import files

        files.WORKSPACE_ROOT = WORKSPACE_ROOT
    except Exception:
        pass

    return WORKSPACE_ROOT


def get_workspace_root() -> Path:
    return WORKSPACE_ROOT
