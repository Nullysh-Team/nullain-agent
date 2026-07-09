"""Papéis de sub-agentes e tools permitidas por papel."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleSpec:
    name: str
    description: str
    tools: tuple[str, ...]
    system_prompt: str
    confirm_all: bool = False


ROLE_SPECS: dict[str, RoleSpec] = {
    "research": RoleSpec(
        name="research",
        description="Pesquisa, leitura de arquivos e síntese de informações.",
        tools=(
            "list_files",
            "read_file",
            "list_skills",
            "run_skill",
        ),
        system_prompt=(
            "Você é o sub-agente Research da NULLAIN. "
            "Foque em coletar fatos, ler arquivos relevantes e sintetizar achados. "
            "Não altere o sistema. Responda em português, de forma objetiva."
        ),
        confirm_all=False,
    ),
    "engineering": RoleSpec(
        name="engineering",
        description="Implementação: leitura, escrita de arquivos e comandos com confirmação.",
        tools=(
            "list_files",
            "read_file",
            "write_file",
            "run_command",
            "list_skills",
            "run_skill",
        ),
        system_prompt=(
            "Você é o sub-agente Engineering da NULLAIN. "
            "Implemente ou corrija código no workspace. "
            "Prefira mudanças mínimas e explique o que fez. "
            "Responda em português."
        ),
        confirm_all=False,
    ),
    "ops": RoleSpec(
        name="ops",
        description="Operações e automações de shell (modo paranoico).",
        tools=(
            "list_files",
            "read_file",
            "run_command",
            "list_skills",
            "run_skill",
        ),
        system_prompt=(
            "Você é o sub-agente Ops da NULLAIN. "
            "Execute automações e diagnósticos com cautela. "
            "Toda tool sensível exige confirmação. Responda em português."
        ),
        confirm_all=True,
    ),
}


def list_roles() -> list[dict[str, object]]:
    return [
        {
            "name": role.name,
            "description": role.description,
            "tools": list(role.tools),
            "confirm_all": role.confirm_all,
        }
        for role in ROLE_SPECS.values()
    ]


def get_role(name: str) -> RoleSpec | None:
    return ROLE_SPECS.get(name)
