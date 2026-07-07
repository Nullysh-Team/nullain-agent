import json
import re
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from nullain import memory
from nullain.llm import complete
from nullain.tools import (
    TOOL_REGISTRY,
    execute_tool,
    get_tool_schemas,
    parse_tool_arguments,
)

ConfirmFn = Callable[[str], bool]
EventFn = Callable[[dict[str, Any]], None]

MAX_ITERATIONS = 10


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


def _tool_call_from_native(tool_call: Any) -> ToolCall:
    return ToolCall(
        id=tool_call.id,
        name=tool_call.function.name,
        arguments=tool_call.function.arguments or "{}",
    )


def _tool_call_from_dict(payload: dict[str, Any]) -> ToolCall | None:
    name = payload.get("name")
    if not name or name not in TOOL_REGISTRY:
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


def _json_candidates(content: str) -> list[str]:
    text = content.strip()
    candidates = [text]

    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates[:0] = [block.strip() for block in fenced if block.strip()]

    return candidates


def _parse_text_tool_calls(content: str) -> list[ToolCall]:
    for candidate in _json_candidates(content):
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
            call = _tool_call_from_dict(payload)
            if call is not None:
                calls.append(call)

        if calls:
            return calls

    return []


def _resolve_tool_calls(message: Any) -> list[ToolCall]:
    if message.tool_calls:
        return [_tool_call_from_native(tool_call) for tool_call in message.tool_calls]

    content = (message.content or "").strip()
    if content:
        return _parse_text_tool_calls(content)

    return []


def _assistant_message(message: Any, tool_calls: list[ToolCall] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }

    resolved = tool_calls or (
        [_tool_call_from_native(tool_call) for tool_call in message.tool_calls]
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


def _emit(on_event: EventFn | None, payload: dict[str, Any]) -> None:
    if on_event is not None:
        on_event(payload)


def run_agent(
    messages: list[dict[str, Any]],
    confirm: ConfirmFn,
    model: str | None = None,
    console: Console | None = None,
    on_event: EventFn | None = None,
    session_id: str | None = None,
) -> str:
    tools = get_tool_schemas()

    for _ in range(MAX_ITERATIONS):
        _emit(on_event, {"type": "thinking"})

        status_ctx = (
            console.status("[bold]NULLAIN pensando...[/bold]")
            if console is not None
            else nullcontext()
        )

        with status_ctx:
            response = complete(messages, model=model, tools=tools)

        message = response.choices[0].message
        tool_calls = _resolve_tool_calls(message)

        if tool_calls:
            messages.append(_assistant_message(message, tool_calls))

            for tool_call in tool_calls:
                arguments = parse_tool_arguments(tool_call.arguments)

                if console is not None:
                    console.print(f"[dim]Tool: {tool_call.name}({arguments})[/dim]")

                _emit(
                    on_event,
                    {
                        "type": "tool_call",
                        "name": tool_call.name,
                        "arguments": arguments,
                    },
                )

                result = execute_tool(tool_call.name, arguments, confirm=confirm)
                memory.log_tool_call(
                    tool_call.name,
                    arguments,
                    result,
                    session_id=session_id,
                )

                _emit(
                    on_event,
                    {
                        "type": "tool_result",
                        "name": tool_call.name,
                        "result": result,
                    },
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

        messages.append({"role": "assistant", "content": content})
        _emit(on_event, {"type": "answer", "content": content})
        return content

    raise RuntimeError("Limite de iterações do agente atingido (10).")