"""Grava nota em notes/ dentro do workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def run(input_text: str = "", confirm=None) -> str:
    from nullain.tools import files

    text = (input_text or "").strip()
    if not text:
        return "Erro: input vazio — envie o texto da nota."

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rel_path = f"notes/note-{stamp}.md"
    content = f"# Nota {stamp}\n\n{text}\n"

    # Reutiliza write_file (jail + confirmação)
    return files.write_file(rel_path, content, confirm=confirm)
