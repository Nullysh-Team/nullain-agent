"""Harness de coding: prompt especializado + tools de engenharia + budget."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from nullain.core_agent import Agent, ConfirmFn, EventFn
from nullain.tools import restricted

CODING_SYSTEM_PROMPT = """Você é NULLAIN-CODING, harness de engenharia acoplado ao runtime NULLAIN.

Regras:
1. Mudanças mínimas e verificáveis — não refatore o que não precisa.
2. Antes de editar: leia o arquivo (read_file) e entenda o contexto.
3. Depois de editar: se possível rode testes ou um comando de verificação (run_command).
4. Nunca invente APIs — prefira o que existe no workspace.
5. Explique o diff conceitual no final (arquivos tocados + por quê).
6. No Windows use PowerShell/cmd; no Unix use shell POSIX.
7. Responda em português.

Fluxo preferido: inspecionar → planejar mentalmente → editar → verificar → resumir.
"""


@dataclass
class CodingBudget:
    max_iterations: int = 12
    max_wall_seconds: float = 600.0


@dataclass
class CodingResult:
    goal: str
    output: str
    duration_ms: float = 0.0
    session_id: str | None = None
    ok: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "ok": self.ok,
            "error": self.error,
        }


CODING_TOOLS = (
    "list_files",
    "read_file",
    "write_file",
    "run_command",
    "list_skills",
    "run_skill",
    "run_engineering_loop",  # opcional se já registrado; restricted ignora se faltar
)


class CodingHarness:
    """Agente especializado em tarefas de código com tools e prompt fixos."""

    def __init__(
        self,
        *,
        budget: CodingBudget | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        tool_names: list[str] | None = None,
    ) -> None:
        self.budget = budget or CodingBudget()
        self.model = model
        self.system_prompt = system_prompt or CODING_SYSTEM_PROMPT
        self.tool_names = list(tool_names or CODING_TOOLS)

    def run(
        self,
        goal: str,
        confirm: ConfirmFn,
        *,
        on_event: EventFn | None = None,
        session_id: str | None = None,
        context: str = "",
    ) -> CodingResult:
        started = time.monotonic()
        sid = session_id or str(uuid.uuid4())

        def emit(payload: dict[str, Any]) -> None:
            if on_event is not None:
                on_event(payload)

        emit({"type": "coding_start", "goal": goal, "session_id": sid})

        user_block = f"Tarefa de engenharia:\n{goal}"
        if context.strip():
            user_block += f"\n\nContexto adicional:\n{context.strip()}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]

        try:
            agent = Agent(
                restricted(self.tool_names),
                confirm,
                model=self.model,
                max_iterations=self.budget.max_iterations,
                on_event=on_event,
                session_id=f"{sid}:coding",
                parallel_tools=True,
            )
            output = agent.run(messages)
            result = CodingResult(
                goal=goal,
                output=output,
                duration_ms=(time.monotonic() - started) * 1000,
                session_id=sid,
                ok=True,
            )
        except Exception as exc:
            result = CodingResult(
                goal=goal,
                output="",
                duration_ms=(time.monotonic() - started) * 1000,
                session_id=sid,
                ok=False,
                error=str(exc),
            )

        emit(
            {
                "type": "coding_done",
                "ok": result.ok,
                "duration_ms": result.duration_ms,
                "error": result.error,
            }
        )
        return result


def build_coding_tools() -> dict[str, dict[str, Any]]:
    def run_coding_task(
        goal: str,
        confirm: ConfirmFn | None = None,
        context: str = "",
    ) -> str:
        if confirm is None:
            return (
                "Erro: run_coding_task exige confirmação, "
                "mas nenhum confirmador foi fornecido."
            )
        preview = f"Iniciar NULLAIN-CODING\n\nTarefa:\n{goal}"
        if not confirm(preview):
            return "Operação cancelada pelo usuário."

        from nullain.config import get_settings

        settings = get_settings()
        budget = CodingBudget(
            max_iterations=settings.nullain_coding_max_iterations,
            max_wall_seconds=settings.nullain_coding_max_wall_seconds,
        )
        # Não incluir run_engineering_loop para evitar recursão acidental
        harness = CodingHarness(
            budget=budget,
            tool_names=[
                "list_files",
                "read_file",
                "write_file",
                "run_command",
                "list_skills",
                "run_skill",
            ],
        )
        result = harness.run(goal, confirm=confirm, context=context)
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    return {
        "run_coding_task": {
            "needs_confirmation": True,
            "source": "coding",
            "fn": run_coding_task,
            "schema": {
                "type": "function",
                "function": {
                    "name": "run_coding_task",
                    "description": (
                        "NULLAIN-CODING: harness de engenharia para implementar, "
                        "corrigir ou revisar código no workspace com fluxo "
                        "inspecionar→editar→verificar."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {
                                "type": "string",
                                "description": "Tarefa de código a executar.",
                            },
                            "context": {
                                "type": "string",
                                "description": "Contexto opcional (erros, arquivos, specs).",
                            },
                        },
                        "required": ["goal"],
                    },
                },
            },
        },
    }
