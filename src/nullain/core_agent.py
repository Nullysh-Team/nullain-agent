from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from nullain import memory
from nullain.history import trim_history
from nullain.llm import complete, complete_stream
from nullain.tools import ToolRegistry, parse_tool_arguments
from nullain.ui.spinner import status

ConfirmFn = Callable[[str], bool]
EventFn = Callable[[dict[str, Any]], None]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


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

    def run(self, messages: list[dict[str, Any]]) -> str:
        tools = self.registry.schemas()

        for _ in range(self.max_iterations):
            messages[:] = trim_history(messages, model=self.model)

            self._emit({"type": "thinking"})

            streamed_to_console = False

            def _on_chunk(chunk: str) -> None:
                nonlocal streamed_to_console
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
                except Exception:
                    response = complete(
                        messages,
                        model=self.model,
                        tools=tools,
                        temperature=self.temperature,
                    )

            message = response.choices[0].message
            tool_calls = self._resolve_tool_calls(message)

            if tool_calls:
                messages.append(self._assistant_message(message, tool_calls))

                for tool_call in tool_calls:
                    arguments = parse_tool_arguments(tool_call.arguments)

                    if self.console is not None:
                        self.console.print(f"[dim]Tool: {tool_call.name}({arguments})[/dim]")

                    self._emit(
                        {
                            "type": "tool_call",
                            "name": tool_call.name,
                            "arguments": arguments,
                        }
                    )

                    with status(self.console, "tool_call"):
                        result = self._execute_tool_call(tool_call.name, arguments)
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
                        }
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )
                continue

            content = (message.content or "").strip()
            if not content:
                raise RuntimeError("O modelo retornou uma resposta vazia.")

            if streamed_to_console and self.console is not None:
                self.console.print()

            messages.append({"role": "assistant", "content": content})
            self._emit({"type": "answer", "content": content})
            return content

        raise RuntimeError(f"Limite de iterações do agente atingido ({self.max_iterations}).")