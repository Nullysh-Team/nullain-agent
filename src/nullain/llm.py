from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from nullain.runtime import get_active_model, get_active_temperature

logger = logging.getLogger("nullain.llm")

_RETRY_DELAYS = (1.0, 2.0, 4.0)
_MAX_JITTER = 0.5
_MAX_ATTEMPTS = 3

_TRANSIENT_ERRORS = (
    RateLimitError,
    APIConnectionError,
    InternalServerError,
    ServiceUnavailableError,
    Timeout,
)

_NON_RETRY_ERRORS = (
    AuthenticationError,
    BadRequestError,
)


class LLMStreamError(Exception):
    """Erro durante streaming — o chamador decide se faz fallback blocking."""


class LLMNetworkError(Exception):
    """Erro de rede/transiente que pode justificar retry ou fallback."""


@dataclass
class _FunctionCall:
    name: str
    arguments: str


@dataclass
class _ToolCallMessage:
    id: str
    function: _FunctionCall


@dataclass
class _StreamedMessage:
    content: str
    tool_calls: list[_ToolCallMessage] | None


@dataclass
class _StreamedChoice:
    message: _StreamedMessage


@dataclass
class _StreamedResponse:
    choices: list[_StreamedChoice]


def _build_kwargs(
    messages: list[dict[str, Any]],
    model: str | None,
    tools: list[dict[str, Any]] | None,
    temperature: float | None,
    stream: bool = False,
) -> dict[str, Any]:
    active_model = model or get_active_model()
    active_temperature = temperature if temperature is not None else get_active_temperature()

    kwargs: dict[str, Any] = {
        "model": active_model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    if active_temperature is not None:
        kwargs["temperature"] = active_temperature
    if stream:
        kwargs["stream"] = True
    return kwargs


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, _NON_RETRY_ERRORS):
        return False
    return isinstance(exc, _TRANSIENT_ERRORS)


def _call_with_retry(operation: Callable[[], Any]) -> Any:
    last_exc: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            if not _should_retry(exc):
                raise
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                jitter = random.uniform(0, _MAX_JITTER)
                time.sleep(_RETRY_DELAYS[attempt] + jitter)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Falha inesperada ao chamar o modelo.")


def _accumulate_tool_call_delta(
    tool_calls_acc: dict[int, dict[str, Any]],
    tool_call_delta: Any,
) -> None:
    index = tool_call_delta.index
    if index is None:
        return

    accumulated = tool_calls_acc.setdefault(
        index,
        {
            "id": "",
            "type": "function",
            "function": {"name": "", "arguments": ""},
        },
    )

    if tool_call_delta.id:
        accumulated["id"] = tool_call_delta.id

    function_delta = tool_call_delta.function
    if function_delta is None:
        return

    if function_delta.name:
        accumulated["function"]["name"] += function_delta.name
    if function_delta.arguments:
        accumulated["function"]["arguments"] += function_delta.arguments


def _build_streamed_response(
    content_parts: list[str],
    tool_calls_acc: dict[int, dict[str, Any]],
) -> _StreamedResponse:
    content = "".join(content_parts)
    tool_calls: list[_ToolCallMessage] | None = None

    if tool_calls_acc:
        tool_calls = []
        for index in sorted(tool_calls_acc):
            payload = tool_calls_acc[index]
            tool_calls.append(
                _ToolCallMessage(
                    id=payload["id"],
                    function=_FunctionCall(
                        name=payload["function"]["name"],
                        arguments=payload["function"]["arguments"] or "{}",
                    ),
                )
            )

    message = _StreamedMessage(content=content, tool_calls=tool_calls or None)
    return _StreamedResponse(choices=[_StreamedChoice(message=message)])


def _collect_stream(
    kwargs: dict[str, Any],
    on_chunk: Callable[[str], None] | None,
) -> _StreamedResponse:
    try:
        stream = litellm.completion(**kwargs)
    except Exception as exc:
        if _should_retry(exc):
            raise LLMNetworkError(str(exc)) from exc
        raise

    content_parts: list[str] = []
    tool_calls_acc: dict[int, dict[str, Any]] = {}

    try:
        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                if on_chunk is not None:
                    on_chunk(delta.content)

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    _accumulate_tool_call_delta(tool_calls_acc, tool_call_delta)
    except Exception as exc:
        if content_parts or tool_calls_acc:
            raise LLMStreamError(
                f"Stream interrompido após conteúdo parcial: {exc}"
            ) from exc
        if _should_retry(exc):
            raise LLMNetworkError(str(exc)) from exc
        raise LLMStreamError(str(exc)) from exc

    return _build_streamed_response(content_parts, tool_calls_acc)


def complete(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
) -> Any:
    kwargs = _build_kwargs(messages, model, tools, temperature)

    return _call_with_retry(lambda: litellm.completion(**kwargs))


def complete_stream(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> Any:
    kwargs = _build_kwargs(messages, model, tools, temperature, stream=True)

    return _call_with_retry(lambda: _collect_stream(kwargs, on_chunk))


def complete_with_fallback(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> Any:
    """Tenta streaming; se falhar de forma recuperável, faz fallback blocking logado."""
    try:
        return complete_stream(
            messages,
            model=model,
            tools=tools,
            temperature=temperature,
            on_chunk=on_chunk,
        )
    except LLMNetworkError as exc:
        logger.warning("Stream falhou (rede), fallback para blocking: %s", exc)
        return complete(messages, model=model, tools=tools, temperature=temperature)
    except LLMStreamError as exc:
        logger.warning("Stream falhou, fallback para blocking: %s", exc)
        return complete(messages, model=model, tools=tools, temperature=temperature)


def chat(messages: list[dict[str, Any]], model: str | None = None) -> str:
    response = complete(messages, model=model)
    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("O modelo retornou uma resposta vazia.")

    return content


def extract_usage(response: Any) -> dict[str, int | None]:
    """Extrai tokens in/out do objeto de resposta do LiteLLM."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"tokens_in": None, "tokens_out": None}

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)

    return {
        "tokens_in": int(prompt_tokens) if prompt_tokens is not None else None,
        "tokens_out": int(completion_tokens) if completion_tokens is not None else None,
    }