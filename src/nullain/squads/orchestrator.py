"""Orquestrador multi-agente com budget e isolamento por ToolRegistry."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nullain.core_agent import Agent, ConfirmFn, EventFn
from nullain.llm import complete
from nullain.squads.roles import ROLE_SPECS, RoleSpec, get_role
from nullain.tools import ToolRegistry, restricted


@dataclass
class SquadBudget:
    max_roles: int = 3
    max_iterations_per_agent: int = 5
    max_wall_seconds: float = 300.0


@dataclass
class RoleRunResult:
    role: str
    subtask: str
    output: str
    ok: bool
    duration_ms: float
    error: str | None = None


@dataclass
class SquadResult:
    goal: str
    plan: list[dict[str, str]]
    role_results: list[RoleRunResult] = field(default_factory=list)
    summary: str = ""
    duration_ms: float = 0.0
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "plan": self.plan,
            "role_results": [
                {
                    "role": r.role,
                    "subtask": r.subtask,
                    "output": r.output,
                    "ok": r.ok,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.role_results
            ],
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
        }


def plan_roles_heuristic(goal: str, max_roles: int = 3) -> list[tuple[str, str]]:
    """Roteamento por palavras-chave; cobre research / engineering / ops."""
    goal_l = goal.lower()
    tasks: list[tuple[str, str]] = []

    research_keys = (
        "pesquis",
        "analis",
        "research",
        "buscar",
        "entender",
        "resumo",
        "investig",
        "ler ",
        "leitura",
    )
    eng_keys = (
        "código",
        "codigo",
        "code",
        "implement",
        "escrev",
        "fix",
        "bug",
        "refator",
        "arquivo",
        "função",
        "funcao",
        "teste",
    )
    ops_keys = (
        "deploy",
        "ops",
        "comando",
        "shell",
        "automat",
        "instalar",
        "servidor",
        "pipeline",
        "cron",
    )

    if any(k in goal_l for k in research_keys):
        tasks.append(("research", f"Pesquise e sintetize o necessário para: {goal}"))
    if any(k in goal_l for k in eng_keys):
        tasks.append(("engineering", f"Implemente ou corrija o necessário para: {goal}"))
    if any(k in goal_l for k in ops_keys):
        tasks.append(("ops", f"Execute operações/automações necessárias para: {goal}"))

    if not tasks:
        # Default: research + engineering para objetivos genéricos
        tasks = [
            ("research", f"Analise o contexto e levante fatos para: {goal}"),
            ("engineering", f"Proponha e aplique a solução para: {goal}"),
        ]

    # Dedup por role mantendo ordem
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for role, subtask in tasks:
        if role in seen or role not in ROLE_SPECS:
            continue
        seen.add(role)
        ordered.append((role, subtask))
        if len(ordered) >= max_roles:
            break
    return ordered


def plan_roles_with_llm(goal: str, max_roles: int = 3) -> list[tuple[str, str]] | None:
    """Tenta plano via LLM (JSON). Fallback None se falhar."""
    roles_doc = ", ".join(ROLE_SPECS.keys())
    prompt = (
        "Decomponha o objetivo em sub-tarefas para sub-agentes.\n"
        f"Papéis válidos: {roles_doc}.\n"
        f"Máximo de {max_roles} itens.\n"
        "Responda APENAS com JSON array: "
        '[{"role":"research","subtask":"..."}, ...]\n\n'
        f"Objetivo: {goal}"
    )
    try:
        response = complete(
            [
                {"role": "system", "content": "Você planeja squads multi-agente. Só JSON."},
                {"role": "user", "content": prompt},
            ],
            tools=None,
            temperature=0.2,
        )
        content = (response.choices[0].message.content or "").strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL | re.I)
        if fenced:
            content = fenced.group(1).strip()
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return None
        plan: list[tuple[str, str]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            subtask = str(item.get("subtask", "")).strip()
            if role in ROLE_SPECS and subtask:
                plan.append((role, subtask))
            if len(plan) >= max_roles:
                break
        return plan or None
    except Exception:
        return None


class SquadOrchestrator:
    def __init__(
        self,
        *,
        budget: SquadBudget | None = None,
        model: str | None = None,
        use_llm_planner: bool = True,
    ) -> None:
        self.budget = budget or SquadBudget()
        self.model = model
        self.use_llm_planner = use_llm_planner

    def build_plan(self, goal: str) -> list[tuple[str, str]]:
        if self.use_llm_planner:
            llm_plan = plan_roles_with_llm(goal, max_roles=self.budget.max_roles)
            if llm_plan:
                return llm_plan
        return plan_roles_heuristic(goal, max_roles=self.budget.max_roles)

    def _registry_for_role(self, role: RoleSpec) -> ToolRegistry:
        # restricted() avisa se tool não existe (ex.: skills ainda não carregadas)
        return restricted(list(role.tools))

    def run(
        self,
        goal: str,
        confirm: ConfirmFn,
        *,
        on_event: EventFn | None = None,
        session_id: str | None = None,
        plan: list[tuple[str, str]] | None = None,
    ) -> SquadResult:
        started = time.monotonic()
        sid = session_id or str(uuid.uuid4())
        resolved_plan = plan or self.build_plan(goal)
        result = SquadResult(
            goal=goal,
            plan=[{"role": r, "subtask": s} for r, s in resolved_plan],
            session_id=sid,
        )

        def emit(payload: dict[str, Any]) -> None:
            if on_event is not None:
                on_event(payload)

        emit({"type": "squad_plan", "plan": result.plan, "session_id": sid})

        context_blocks: list[str] = []

        for role_name, subtask in resolved_plan:
            elapsed = time.monotonic() - started
            if elapsed > self.budget.max_wall_seconds:
                result.role_results.append(
                    RoleRunResult(
                        role=role_name,
                        subtask=subtask,
                        output="",
                        ok=False,
                        duration_ms=0.0,
                        error="Budget de tempo do squad esgotado.",
                    )
                )
                break

            role = get_role(role_name)
            if role is None:
                result.role_results.append(
                    RoleRunResult(
                        role=role_name,
                        subtask=subtask,
                        output="",
                        ok=False,
                        duration_ms=0.0,
                        error=f"Papel desconhecido: {role_name}",
                    )
                )
                continue

            emit(
                {
                    "type": "squad_role_start",
                    "role": role_name,
                    "subtask": subtask,
                }
            )

            role_start = time.monotonic()
            registry = self._registry_for_role(role)
            prior = "\n\n".join(context_blocks[-3:]) if context_blocks else "(nenhum)"
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": role.system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Objetivo global do squad:\n{goal}\n\n"
                        f"Sua subtarefa:\n{subtask}\n\n"
                        f"Contexto de papéis anteriores:\n{prior}"
                    ),
                },
            ]

            try:
                agent = Agent(
                    registry,
                    confirm,
                    model=self.model,
                    max_iterations=self.budget.max_iterations_per_agent,
                    on_event=on_event,
                    confirm_all=role.confirm_all,
                    session_id=f"{sid}:{role_name}",
                    parallel_tools=True,
                )
                output = agent.run(messages)
                duration_ms = (time.monotonic() - role_start) * 1000
                role_result = RoleRunResult(
                    role=role_name,
                    subtask=subtask,
                    output=output,
                    ok=True,
                    duration_ms=duration_ms,
                )
                context_blocks.append(f"## {role_name}\n{output}")
            except Exception as exc:
                duration_ms = (time.monotonic() - role_start) * 1000
                role_result = RoleRunResult(
                    role=role_name,
                    subtask=subtask,
                    output="",
                    ok=False,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                context_blocks.append(f"## {role_name} (erro)\n{exc}")

            result.role_results.append(role_result)
            emit(
                {
                    "type": "squad_role_end",
                    "role": role_name,
                    "ok": role_result.ok,
                    "output": role_result.output,
                    "error": role_result.error,
                    "duration_ms": role_result.duration_ms,
                }
            )

        result.summary = self._synthesize(goal, result.role_results)
        result.duration_ms = (time.monotonic() - started) * 1000
        emit(
            {
                "type": "squad_done",
                "summary": result.summary,
                "duration_ms": result.duration_ms,
            }
        )
        return result

    def _synthesize(self, goal: str, role_results: list[RoleRunResult]) -> str:
        if not role_results:
            return "Squad não executou nenhum papel."

        blocks = []
        for item in role_results:
            if item.ok:
                blocks.append(f"### {item.role}\n{item.output}")
            else:
                blocks.append(f"### {item.role} (falhou)\n{item.error or 'erro'}")

        transcript = "\n\n".join(blocks)
        try:
            response = complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Você consolida resultados de um squad multi-agente. "
                            "Produza um resumo final claro em português."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Objetivo: {goal}\n\n"
                            f"Resultados por papel:\n{transcript}\n\n"
                            "Entregue: status geral, o que foi feito, riscos e próximos passos."
                        ),
                    },
                ],
                model=self.model,
                tools=None,
                temperature=0.3,
            )
            content = (response.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception:
            pass

        # Fallback sem LLM
        return f"Objetivo: {goal}\n\n" + transcript


def build_squad_tools() -> dict[str, dict[str, Any]]:
    """Tool run_squad exposta ao agente principal."""

    def list_squad_roles() -> str:
        from nullain.squads.roles import list_roles

        return json.dumps(list_roles(), indent=2, ensure_ascii=False)

    def run_squad(
        goal: str,
        confirm: ConfirmFn | None = None,
    ) -> str:
        if confirm is None:
            return (
                "Erro: run_squad exige confirmação, mas nenhum confirmador foi fornecido."
            )
        preview = f"Iniciar SQUAD multi-agente\n\nObjetivo:\n{goal}"
        if not confirm(preview):
            return "Operação cancelada pelo usuário."

        orchestrator = SquadOrchestrator(use_llm_planner=True)
        result = orchestrator.run(goal, confirm=confirm)
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    return {
        "list_squad_roles": {
            "needs_confirmation": False,
            "source": "squad",
            "fn": list_squad_roles,
            "schema": {
                "type": "function",
                "function": {
                    "name": "list_squad_roles",
                    "description": "Lista papéis disponíveis do NULLAIN-SQUADS.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        },
        "run_squad": {
            "needs_confirmation": True,
            "source": "squad",
            "fn": run_squad,
            "schema": {
                "type": "function",
                "function": {
                    "name": "run_squad",
                    "description": (
                        "Orquestra sub-agentes (research, engineering, ops) para um "
                        "objetivo complexo. Exige confirmação. Use para tarefas multi-etapa."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {
                                "type": "string",
                                "description": "Objetivo completo do squad.",
                            }
                        },
                        "required": ["goal"],
                    },
                },
            },
        },
    }
