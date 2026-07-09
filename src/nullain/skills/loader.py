"""Carrega skills a partir de pastas com SKILL.md (+ handler.py opcional)."""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillDefinition:
    name: str
    description: str
    body: str
    path: Path
    needs_confirmation: bool = False
    tools: list[str] = field(default_factory=list)
    handler: Callable[..., str] | None = None
    source_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "needs_confirmation": self.needs_confirmation,
            "tools": list(self.tools),
            "has_handler": self.handler is not None,
            "path": str(self.path),
        }


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    text = raw.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not match:
        return {}, text

    meta_block, body = match.group(1), match.group(2)
    meta: dict[str, Any] = {}
    for line in meta_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.lower() in {"true", "yes"}:
            meta[key] = True
        elif value.lower() in {"false", "no"}:
            meta[key] = False
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [
                    item.strip().strip('"').strip("'")
                    for item in inner.split(",")
                    if item.strip()
                ]
        else:
            meta[key] = value
    return meta, body.strip()


def _load_handler(skill_dir: Path, skill_name: str) -> Callable[..., str] | None:
    handler_path = skill_dir / "handler.py"
    if not handler_path.exists():
        return None

    module_name = f"nullain_skill_{skill_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None

    run_fn = getattr(module, "run", None)
    if not callable(run_fn):
        return None
    return run_fn  # type: ignore[return-value]


def parse_skill_file(skill_md: Path) -> SkillDefinition:
    raw = skill_md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    skill_dir = skill_md.parent
    name = str(meta.get("name") or skill_dir.name).strip()
    description = str(meta.get("description") or f"Skill {name}").strip()
    needs_confirmation = bool(meta.get("needs_confirmation", False))
    tools_raw = meta.get("tools") or []
    if isinstance(tools_raw, str):
        tools = [tools_raw]
    else:
        tools = [str(item) for item in tools_raw]

    handler = _load_handler(skill_dir, name)
    return SkillDefinition(
        name=name,
        description=description,
        body=body,
        path=skill_md,
        needs_confirmation=needs_confirmation,
        tools=tools,
        handler=handler,
        source_dir=skill_dir,
    )


def discover_skills(roots: list[Path]) -> dict[str, SkillDefinition]:
    found: dict[str, SkillDefinition] = {}
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                skill = parse_skill_file(skill_md)
            except Exception:
                continue
            found[skill.name] = skill
    return found


def skills_dir_candidates() -> list[Path]:
    from nullain.config import get_settings

    settings = get_settings()
    configured = (settings.nullain_skills_dir or "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser().resolve())
    candidates.append(Path.cwd() / "skills")
    # Skills empacotadas junto ao código (fallback de exemplos)
    package_skills = Path(__file__).resolve().parent.parent.parent.parent / "skills"
    if package_skills not in candidates:
        candidates.append(package_skills)
    return candidates
