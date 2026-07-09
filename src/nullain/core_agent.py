from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from nullain import memory
from nullain.history import trim_history
from nullain.llm import complete, complete_stream, extract_usage
from nullain.tools import ToolRegistry, parse_tool_arguments
from nullain.ui.spinner import status

ConfirmFn = Callable[[str], bool]
EventFn = Callable[[dict[str, Any]], None]

CONFIRM_TIMEOUT_SECONDS = 120.0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class _TurnStats:
    turn_start: float = 0.0
    ttft_ms: float | None = None
    tool_durations: list[float] = field(default_factory=list)
    iterations: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None


def _confirm_timeout() -> float:
    try:
        from nullain.config import get_settings

        value = get_settings().nullain_confirm_timeout_seconds
        if value and value > 0:
            return float(value)
    except Exception:
        pass
    return float(CONFIRM_TIMEOUT_SECONDS)


def _confirm_with_timeout(confirm: ConfirmFn, preview: str) -> bool:
    """Executa confirmação com timeout — evita travar o turno indefinidamente."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(confirm, preview)
        try:
            return future.result(timeout=_confirm_timeout())
        except concurrent.futures.TimeoutError:
            return False


class Agent:
    def __init__(
        self,
        registry: ToolRegistry,
        confirm: ConfirmFn,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_iterations: int = 10,
        system_prompt: str | None = None,
        on_event: EventFn | None = None,
        confirm_all: bool = False,
        console: Console | None = None,
        session_id: str | None = None,
        parallel_tools: bool = True,
    ) -> None:
        self.registry = ToolRegistry(
            dict(registry._tools),
            mcp_manager=registry._mcp_manager,
            confirm_all=confirm_all or registry.confirm_all,
        )
        self.confirm = confirm
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.on_event = on_event
        self.console = console
        self.session_id = session_id
        self.parallel_tools = parallel_tools

    def _tool_call_from_native(self, tool_call: Any) -> ToolCall:
        return ToolCall(
            id=tool_call.id,
            name=tool_call.function.name,
            arguments=tool_call.function.arguments or "{}",
        )

    def _tool_call_from_dict(self, payload: dict[str, Any]) -> ToolCall | None:
        name = payload.get("name")
        if not name or name not in self.registry:
            return None

        raw_args = payload.get("arguments", payload.get("parameters", {}))
        if isinstance(raw_args, str):
            arguments = raw_args
        else:
            arguments = json.dumps(raw_args)

        return ToolCall(
            id=f"call_{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        )

    def _json_candidates(self, content: str) -> list[str]:
        text = content.strip()
        candidates = [text]

        fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates[:0] = [block.strip() for block in fenced if block.strip()]

        return candidates

    def _parse_text_tool_calls(self, content: str) -> list[ToolCall]:
        for candidate in self._json_candidates(content):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            payloads: list[dict[str, Any]]
            if isinstance(parsed, dict):
                payloads = [parsed]
            elif isinstance(parsed, list):
                payloads = [item for item in parsed if isinstance(item, dict)]
            else:
                continue

            calls: list[ToolCall] = []
            for payload in payloads:
                call = self._tool_call_from_dict(payload)
                if call is not None:
                    calls.append(call)

            if calls:
                return calls

        return []

    def _resolve_tool_calls(self, message: Any) -> list[ToolCall]:
        if message.tool_calls:
            return [self._tool_call_from_native(tool_call) for tool_call in message.tool_calls]

        content = (message.content or "").strip()
        if content:
            return self._parse_text_tool_calls(content)

        return []

    def _assistant_message(
        self,
        message: Any,
        tool_calls: list[ToolCall] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }

        resolved = tool_calls or (
            [self._tool_call_from_native(tool_call) for tool_call in message.tool_calls]
            if message.tool_calls
            else []
        )

        if resolved:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in resolved
            ]

        return payload

    def _emit(self, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            self.on_event(payload)

    def _execute_tool_call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self.registry:
            return f"Erro: tool não permitida para este agente: {name}"
        return self.registry.execute(name, arguments, confirm=self.confirm)

    def _execute_single_tool(
        self,
        tool_call: ToolCall,
        arguments: dict[str, Any],
        stats: _TurnStats,
    ) -> tuple[str, str]:
        """Executa uma tool e retorna (tool_call_id, result)."""
        if self.console is not None:
            self.console.print(f"[dim]Tool: {tool_call.name}({arguments})[/dim]")

        self._emit(
            {
                "type": "tool_call",
                "name": tool_call.name,
                "arguments": arguments,
            }
        )

        tool_start = time.monotonic()
        with status(self.console, "tool_call"):
            result = self._execute_tool_call(tool_call.name, arguments)
        tool_duration = (time.monotonic() - tool_start) * 1000
        stats.tool_durations.append(tool_duration)

        memory.log_tool_call(
            tool_call.name,
            arguments,
            result,
            session_id=self.session_id,
        )

        self._emit(
            {
                "type": "tool_result",
                "name": tool_call.name,
                "result": result,
                "duration_ms": round(tool_duration, 1),
            }
        )

        return tool_call.id, result

    def _execute_tools(
        self,
        tool_calls: list[ToolCall],
        stats: _TurnStats,
    ) -> list[dict[str, Any]]:
        """Executa tool calls — em paralelo se independentes, sequencial caso contrário."""
        parsed: list[tuple[ToolCall, dict[str, Any]]] = []
        for tool_call in tool_calls:
            arguments = parse_tool_arguments(tool_call.arguments)
            parsed.append((tool_call, arguments))

        if not self.parallel_tools or len(parsed) <= 1:
            results: list[dict[str, Any]] = []
            for tool_call, arguments in parsed:
                tool_id, result = self._execute_single_tool(tool_call, arguments, stats)
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result,
                    }
                )
            return results

        with ThreadPoolExecutor(max_workers=min(len(parsed), 4)) as pool:
            futures = {
                pool.submit(self._execute_single_tool, tc, args, stats): tc
                for tc, args in parsed
            }
            ordered: dict[str, str] = {}
            for future in futures:
                tool_id, result = future.result()
                ordered[tool_id] = result

        return [
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": ordered.get(tool_call.id, "Erro: resultado perdido"),
            }
            for tool_call, _ in parsed
        ]

    def _log_metrics(self, stats: _TurnStats) -> None:
        total_ms = (time.monotonic() - stats.turn_start) * 1000
        memory.log_turn_metrics(
            memory.TurnMetrics(
                session_id=self.session_id,
                turn_index=stats.iterations,
                ttft_ms=stats.ttft_ms,
                total_ms=total_ms,
                iterations=stats.iterations,
                tokens_in=stats.tokens_in,
                tokens_out=stats.tokens_out,
                tool_count=len(stats.tool_durations),
                tool_total_ms=sum(stats.tool_durations),
                model=self.model,
            )
        )

    def run(self, messages: list[dict[str, Any]]) -> str:
        tools = self.registry.schemas()
        stats = _TurnStats(turn_start=time.monotonic())

        for _ in range(self.max_iterations):
            messages[:] = trim_history(messages, model=self.model)
            stats.iterations += 1

            self._emit({"type": "thinking"})

            streamed_to_console = False
            first_chunk_time: float | None = None

            def _on_chunk(chunk: str) -> None:
                nonlocal first_chunk_time, streamed_to_console
                if first_chunk_time is None:
                    first_chunk_time = time.monotonic()
                    stats.ttft_ms = (first_chunk_time - stats.turn_start) * 1000
                self._emit({"type": "answer_chunk", "content": chunk})
                if self.console is not None:
                    self.console.print(chunk, end="")
                    streamed_to_console = True

            with status(self.console, "thinking"):
                try:
                    response = complete_stream(
                        messages,
                        model=self.model,
                        tools=tools,
                        temperature=self.temperature,
                        on_chunk=_on_chunk,
                    )
                except Exception as exc:
                    from nullain.llm import LLMNetworkError, LLMStreamError

                    if isinstance(exc, (LLMNetworkError, LLMStreamError)):
                        response = complete(
                            messages,
                            model=self.model,
                            tools=tools,
                            temperature=self.temperature,
                        )
                    else:
                        raise

            usage = extract_usage(response)
            stats.tokens_in = usage["tokens_in"]
            stats.tokens_out = usage["tokens_out"]

            message = response.choices[0].message
            tool_calls = self._resolve_tool_calls(message)

            if tool_calls:
                messages.append(self._assistant_message(message, tool_calls))

                tool_messages = self._execute_tools(tool_calls, stats)
                messages.extend(tool_messages)
                continue

            content = (message.content or "").strip()
            if not content:
                self._log_metrics(stats)
                raise RuntimeError("O modelo retornou uma resposta vazia.")

            if streamed_to_console and self.console is not None:
                self.console.print()

            messages.append({"role": "assistant", "content": content})
            self._emit({"type": "answer", "content": content})

            self._log_metrics(stats)
            return content

        self._log_metrics(stats)
        raise RuntimeError(f"Limite de iterações do agente atingido ({self.max_iterations}).")