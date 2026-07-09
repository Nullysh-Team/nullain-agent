"""Registro de skills e tools nativas list_skills / run_skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nullain.skills.loader import SkillDefinition, discover_skills, skills_dir_candidates

ConfirmFn = Any

_SKILL_REGISTRY: "SkillRegistry | None" = None


class SkillRegistry:
    def __init__(self, skills: dict[str, SkillDefinition] | None = None) -> None:
        self._skills: dict[str, SkillDefinition] = dict(skills or {})

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def to_public_list(self) -> list[dict[str, Any]]:
        return [skill.to_dict() for skill in self.list()]

    def format_for_prompt(self) -> str:
        if not self._skills:
            return ""
        lines = ["Skills disponíveis (use list_skills / run_skill):"]
        for skill in self.list():
            handler = "handler" if skill.handler else "instruções"
            lines.append(f"- {skill.name}: {skill.description} [{handler}]")
        return "\n".join(lines)

    def reload(self, roots: list[Path] | None = None) -> int:
        search_roots = roots or skills_dir_candidates()
        self._skills = discover_skills(search_roots)
        return len(self._skills)

    def run(
        self,
        name: str,
        input_text: str = "",
        confirm: ConfirmFn | None = None,
    ) -> str:
        skill = self._skills.get(name)
        if skill is None:
            available = ", ".join(self.names()) or "(nenhuma)"
            return f"Erro: skill desconhecida: {name}. Disponíveis: {available}"

        if skill.needs_confirmation:
            if confirm is None:
                return (
                    "Erro: esta skill exige confirmação, "
                    "mas nenhum confirmador foi fornecido."
                )
            preview = (
                f"Skill: {skill.name}\n"
                f"Descrição: {skill.description}\n"
                f"Input:\n{input_text[:500]}"
            )
            if not confirm(preview):
                return "Operação cancelada pelo usuário."

        if skill.handler is not None:
            try:
                result = skill.handler(input_text=input_text, confirm=confirm)
                if not isinstance(result, str):
                    return json.dumps(result, ensure_ascii=False)
                return result
            except TypeError:
                try:
                    result = skill.handler(input_text)
                    return result if isinstance(result, str) else str(result)
                except Exception as exc:
                    return f"Erro ao executar handler da skill {name}: {exc}"
            except Exception as exc:
                return f"Erro ao executar handler da skill {name}: {exc}"

        # Skill sem handler: devolve instruções para o modelo seguir no turno.
        parts = [
            f"# Skill: {skill.name}",
            f"Descrição: {skill.description}",
            "",
            "## Instruções",
            skill.body or "(sem corpo)",
        ]
        if input_text.strip():
            parts.extend(["", "## Input do usuário", input_text.strip()])
        parts.append(
            "\nSiga as instruções acima para resolver o input. "
            "Use tools nativas quando necessário."
        )
        return "\n".join(parts)


def get_skill_registry() -> SkillRegistry:
    global _SKILL_REGISTRY
    if _SKILL_REGISTRY is None:
        _SKILL_REGISTRY = SkillRegistry()
        _SKILL_REGISTRY.reload()
    return _SKILL_REGISTRY


def init_skills(roots: list[Path] | None = None) -> SkillRegistry:
    global _SKILL_REGISTRY
    registry = SkillRegistry()
    registry.reload(roots)
    _SKILL_REGISTRY = registry
    return registry


def reload_skills(roots: list[Path] | None = None) -> int:
    return get_skill_registry().reload(roots)


def build_skill_tools(registry: SkillRegistry | None = None) -> dict[str, dict[str, Any]]:
    """Schemas/fns das tools de skill para o ToolRegistry global."""
    skill_registry = registry or get_skill_registry()

    def list_skills() -> str:
        skills = skill_registry.to_public_list()
        if not skills:
            return "(nenhuma skill carregada — coloque pastas em ./skills/*/SKILL.md)"
        return json.dumps(skills, indent=2, ensure_ascii=False)

    def run_skill(
        name: str,
        input: str = "",
        confirm: ConfirmFn | None = None,
    ) -> str:
        return skill_registry.run(name, input_text=input, confirm=confirm)

    return {
        "list_skills": {
            "needs_confirmation": False,
            "source": "skill",
            "fn": list_skills,
            "schema": {
                "type": "function",
                "function": {
                    "name": "list_skills",
                    "description": (
                        "Lista skills plugáveis disponíveis (NULLAIN-SKILLS) "
                        "com nome, descrição e se têm handler."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        },
        "run_skill": {
            "needs_confirmation": False,  # confirmação por skill.needs_confirmation
            "source": "skill",
            "fn": run_skill,
            "schema": {
                "type": "function",
                "function": {
                    "name": "run_skill",
                    "description": (
                        "Executa ou carrega uma skill pelo nome. "
                        "Skills com handler rodam código; sem handler devolvem "
                        "instruções para o agente seguir."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Nome da skill (ex.: echo, note).",
                            },
                            "input": {
                                "type": "string",
                                "description": "Entrada/contexto para a skill.",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
        },
    }
