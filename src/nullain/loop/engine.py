"""Loop Engineering: plan → act → evaluate → replan com budget e checkpoints."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nullain.core_agent import Agent, ConfirmFn, EventFn
from nullain.llm import complete
from nullain.tools import restricted


@dataclass
class LoopBudget:
    max_cycles: int = 5
    max_iterations_per_cycle: int = 6
    max_wall_seconds: float = 600.0
    require_checkpoint: bool = False  # confirmação humana entre ciclos


@dataclass
class LoopCycleResult:
    cycle: int
    plan: str
    action_output: str
    evaluation: str
    done: bool
    score: float | None = None
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class LoopResult:
    goal: str
    cycles: list[LoopCycleResult] = field(default_factory=list)
    final_output: str = ""
    converged: bool = False
    duration_ms: float = 0.0
    session_id: str | None = None
    stop_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "cycles": [
                {
                    "cycle": c.cycle,
                    "plan": c.plan,
                    "action_output": c.action_output,
                    "evaluation": c.evaluation,
                    "done": c.done,
                    "score": c.score,
                    "duration_ms": c.duration_ms,
                    "error": c.error,
                }
                for c in self.cycles
            ],
            "final_output": self.final_output,
            "converged": self.converged,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "stop_reason": self.stop_reason,
        }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.I)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _llm_text(messages: list[dict[str, Any]], model: str | None = None) -> str:
    response = complete(messages, model=model, tools=None, temperature=0.2)
    return (response.choices[0].message.content or "").strip()


class EngineeringLoop:
    """Ciclo controlado até convergência ou esgotamento do budget."""

    DEFAULT_TOOLS = (
        "list_files",
        "read_file",
        "write_file",
        "run_command",
        "list_skills",
        "run_skill",
    )

    def __init__(
        self,
        *,
        budget: LoopBudget | None = None,
        model: str | None = None,
        tool_names: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.budget = budget or LoopBudget()
        self.model = model
        self.tool_names = list(tool_names or self.DEFAULT_TOOLS)
        self.system_prompt = system_prompt or (
            "Você é o motor de execução do Loop Engineering da NULLAIN. "
            "Execute o plano com ferramentas, de forma mínima e verificável. "
            "Responda em português ao final do ciclo com o que foi feito."
        )

    def _registry(self):
        return restricted(self.tool_names)

    def _plan(
        self,
        goal: str,
        history: list[LoopCycleResult],
    ) -> str:
        history_block = "(primeiro ciclo)"
        if history:
            parts = []
            for c in history[-3:]:
                parts.append(
                    f"Ciclo {c.cycle}: done={c.done} score={c.score}\n"
                    f"Plano: {c.plan[:400]}\n"
                    f"Ação: {c.action_output[:600]}\n"
                    f"Eval: {c.evaluation[:400]}"
                )
            history_block = "\n\n".join(parts)

        text = _llm_text(
            [
                {
                    "role": "system",
                    "content": (
                        "Você planeja um único ciclo de trabalho para atingir um objetivo. "
                        "Seja concreto e acionável. Liste 3–7 passos no máximo. "
                        "Não execute tools — só planeje."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Objetivo:\n{goal}\n\n"
                        f"Histórico recente:\n{history_block}\n\n"
                        "Produza o plano do próximo ciclo."
                    ),
                },
            ],
            model=self.model,
        )
        return text or "1. Inspecionar o workspace\n2. Aplicar mudança mínima\n3. Verificar"

    def _act(
        self,
        goal: str,
        plan: str,
        confirm: ConfirmFn,
        on_event: EventFn | None,
        session_id: str,
        cycle: int,
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Objetivo global:\n{goal}\n\n"
                    f"Plano deste ciclo:\n{plan}\n\n"
                    "Execute o plano com as tools disponíveis. "
                    "Ao terminar, resuma o que fez e o estado atual."
                ),
            },
        ]
        agent = Agent(
            self._registry(),
            confirm,
            model=self.model,
            max_iterations=self.budget.max_iterations_per_cycle,
            on_event=on_event,
            session_id=f"{session_id}:c{cycle}",
            parallel_tools=True,
        )
        return agent.run(messages)

    def _evaluate(self, goal: str, plan: str, action_output: str) -> tuple[bool, float, str]:
        """Retorna (done, score 0-1, evaluation text)."""
        prompt = (
            f"Objetivo:\n{goal}\n\n"
            f"Plano do ciclo:\n{plan}\n\n"
            f"Resultado da execução:\n{action_output}\n\n"
            "Avalie se o objetivo foi ATINGIDO.\n"
            "Responda APENAS JSON:\n"
            '{"done": true|false, "score": 0.0-1.0, "rationale": "..."}\n'
            "done=true só se o objetivo está substancialmente cumprido."
        )
        try:
            text = _llm_text(
                [
                    {
                        "role": "system",
                        "content": "Avaliador rigoroso de objetivos. Só JSON válido.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            data = _extract_json_object(text) or {}
            done = bool(data.get("done", False))
            score_raw = data.get("score", 0.0)
            try:
                score = float(score_raw)
            except (TypeError, ValueError):
                score = 1.0 if done else 0.0
            score = max(0.0, min(1.0, score))
            rationale = str(data.get("rationale") or text or "sem rationale")
            # Score alto sem done explícito ainda pode convergir
            if not done and score >= 0.9:
                done = True
            return done, score, rationale
        except Exception as exc:
            # Fallback heurístico: keywords de sucesso no output
            lower = action_output.lower()
            success_hints = ("concluíd", "completo", "done", "sucesso", "pronto", "ok")
            fail_hints = ("erro", "falha", "failed", "não consegui", "bloqueado")
            if any(h in lower for h in fail_hints):
                return False, 0.2, f"Heurística: indícios de falha ({exc})"
            if any(h in lower for h in success_hints):
                return True, 0.75, f"Heurística: indícios de sucesso ({exc})"
            return False, 0.4, f"Avaliação indisponível ({exc}); continua."

    def run(
        self,
        goal: str,
        confirm: ConfirmFn,
        *,
        on_event: EventFn | None = None,
        session_id: str | None = None,
    ) -> LoopResult:
        started = time.monotonic()
        sid = session_id or str(uuid.uuid4())
        result = LoopResult(goal=goal, session_id=sid)

        def emit(payload: dict[str, Any]) -> None:
            if on_event is not None:
                on_event(payload)

        emit({"type": "loop_start", "goal": goal, "session_id": sid})

        for cycle in range(1, self.budget.max_cycles + 1):
            elapsed = time.monotonic() - started
            if elapsed > self.budget.max_wall_seconds:
                result.stop_reason = "budget_time"
                break

            if self.budget.require_checkpoint and cycle > 1:
                preview = (
                    f"Loop Engineering — checkpoint antes do ciclo {cycle}\n"
                    f"Objetivo: {goal}\n"
                    f"Ciclos concluídos: {cycle - 1}"
                )
                if not confirm(preview):
                    result.stop_reason = "checkpoint_denied"
                    break

            cycle_start = time.monotonic()
            emit({"type": "loop_cycle_start", "cycle": cycle})

            try:
                plan = self._plan(goal, result.cycles)
                emit({"type": "loop_plan", "cycle": cycle, "plan": plan})

                action_output = self._act(
                    goal, plan, confirm, on_event, sid, cycle
                )
                emit(
                    {
                        "type": "loop_action",
                        "cycle": cycle,
                        "output": action_output[:2000],
                    }
                )

                done, score, evaluation = self._evaluate(goal, plan, action_output)
                cycle_result = LoopCycleResult(
                    cycle=cycle,
                    plan=plan,
                    action_output=action_output,
                    evaluation=evaluation,
                    done=done,
                    score=score,
                    duration_ms=(time.monotonic() - cycle_start) * 1000,
                )
            except Exception as exc:
                cycle_result = LoopCycleResult(
                    cycle=cycle,
                    plan="",
                    action_output="",
                    evaluation="",
                    done=False,
                    duration_ms=(time.monotonic() - cycle_start) * 1000,
                    error=str(exc),
                )

            result.cycles.append(cycle_result)
            emit(
                {
                    "type": "loop_cycle_end",
                    "cycle": cycle,
                    "done": cycle_result.done,
                    "score": cycle_result.score,
                    "error": cycle_result.error,
                    "duration_ms": cycle_result.duration_ms,
                }
            )

            if cycle_result.done and not cycle_result.error:
                result.converged = True
                result.final_output = cycle_result.action_output
                result.stop_reason = "converged"
                break
        else:
            if not result.stop_reason:
                result.stop_reason = "max_cycles"

        if not result.final_output and result.cycles:
            last = result.cycles[-1]
            result.final_output = last.action_output or last.evaluation or last.error or ""

        result.duration_ms = (time.monotonic() - started) * 1000
        emit(
            {
                "type": "loop_done",
                "converged": result.converged,
                "stop_reason": result.stop_reason,
                "duration_ms": result.duration_ms,
            }
        )
        return result


def build_loop_tools() -> dict[str, dict[str, Any]]:
    """Expõe run_engineering_loop ao agente principal."""

    def run_engineering_loop(
        goal: str,
        confirm: ConfirmFn | None = None,
        max_cycles: int = 5,
    ) -> str:
        if confirm is None:
            return (
                "Erro: run_engineering_loop exige confirmação, "
                "mas nenhum confirmador foi fornecido."
            )
        preview = (
            f"Iniciar Loop Engineering (máx. {max_cycles} ciclos)\n\n"
            f"Objetivo:\n{goal}"
        )
        if not confirm(preview):
            return "Operação cancelada pelo usuário."

        from nullain.config import get_settings

        settings = get_settings()
        budget = LoopBudget(
            max_cycles=max(1, min(int(max_cycles), 10)),
            max_iterations_per_cycle=settings.nullain_loop_max_iterations,
            max_wall_seconds=settings.nullain_loop_max_wall_seconds,
            require_checkpoint=settings.nullain_loop_require_checkpoint,
        )
        engine = EngineeringLoop(budget=budget)
        # Dentro do loop, tools sensíveis ainda pedem confirm via mesmo confirm
        result = engine.run(goal, confirm=confirm)
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    return {
        "run_engineering_loop": {
            "needs_confirmation": True,
            "source": "loop",
            "fn": run_engineering_loop,
            "schema": {
                "type": "function",
                "function": {
                    "name": "run_engineering_loop",
                    "description": (
                        "Loop Engineering: planeja, executa, avalia e re-planeja "
                        "até convergir no objetivo ou esgotar o budget de ciclos. "
                        "Use para tarefas que exigem auto-iteração controlada."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {
                                "type": "string",
                                "description": "Objetivo a atingir.",
                            },
                            "max_cycles": {
                                "type": "integer",
                                "description": "Máximo de ciclos plan→act→eval (1–10).",
                            },
                        },
                        "required": ["goal"],
                    },
                },
            },
        },
    }
