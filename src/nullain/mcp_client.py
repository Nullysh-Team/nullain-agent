import asyncio
import json
import os
import re
import sys
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

try:
    from mcp.client.sse import sse_client
except ImportError:
    sse_client = None  # type: ignore[assignment,misc]

try:
    from mcp.client.streamable_http import streamable_http_client
except ImportError:
    streamable_http_client = None  # type: ignore[assignment,misc]

CONFIG_PATH = Path("mcp.config.json")

WRITE_KEYWORDS = (
    "write",
    "create",
    "update",
    "delete",
    "push",
    "merge",
    "fork",
    "post",
    "put",
    "patch",
    "remove",
)


@dataclass
class McpToolBinding:
    registry_name: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    needs_confirmation: bool


@dataclass
class ServerConnection:
    name: str
    session: ClientSession
    stack: AsyncExitStack


def _substitute_env(value: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return re.sub(r"\$\{([^}]+)\}", replacer, value)


def _resolve_env(env: dict[str, str]) -> dict[str, str]:
    return {key: _substitute_env(value) for key, value in env.items()}


def _resolve_command(command: str) -> str:
    if command in {"python", "python3"}:
        return sys.executable
    return command


def _tool_needs_confirmation(tool_name: str) -> bool:
    lower = tool_name.lower()
    return any(keyword in lower for keyword in WRITE_KEYWORDS)


def _format_call_result(result: types.CallToolResult) -> str:
    prefix = "Erro na tool MCP: " if result.isError else ""
    parts: list[str] = []

    for content in result.content:
        if isinstance(content, types.TextContent):
            parts.append(content.text)
        elif isinstance(content, types.ImageContent):
            parts.append(f"[imagem {content.mimeType}, {len(content.data)} bytes]")
        elif isinstance(content, types.EmbeddedResource):
            resource = content.resource
            if isinstance(resource, types.TextResourceContents):
                parts.append(resource.text)
            else:
                parts.append(f"[recurso {getattr(resource, 'uri', 'desconhecido')}]")
        else:
            parts.append(str(content))

    structured = getattr(result, "structuredContent", None)
    if structured:
        parts.append(json.dumps(structured, ensure_ascii=False))

    output = "\n".join(parts).strip()
    return prefix + (output or "(sem saída)")


class McpManager:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._connected = False
        self._servers: dict[str, ServerConnection] = {}
        self._tool_bindings: dict[str, McpToolBinding] = {}
        self._errors: list[str] = []

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def get_tool_bindings(self) -> dict[str, McpToolBinding]:
        return dict(self._tool_bindings)

    def connect(self, config_path: Path = CONFIG_PATH) -> int:
        if self._connected:
            return len(self._tool_bindings)

        self._start_loop_thread()
        assert self._loop is not None

        future = asyncio.run_coroutine_threadsafe(
            self._connect_async(config_path),
            self._loop,
        )
        try:
            count = future.result(timeout=120)
            self._connected = True
            return count
        except Exception as exc:
            self._errors.append(str(exc))
            return 0

    def disconnect(self) -> None:
        if not self._loop:
            return

        if self._connected:
            future = asyncio.run_coroutine_threadsafe(
                self._disconnect_async(),
                self._loop,
            )
            try:
                future.result(timeout=30)
            except Exception:
                pass

        self._connected = False
        self._servers.clear()
        self._tool_bindings.clear()
        self._stop_loop_thread()

    def call_tool_sync(
        self,
        registry_name: str,
        arguments: dict[str, Any],
        confirm,
    ) -> str:
        if not self._loop or not self._connected:
            return "Erro: MCP não conectado."

        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(registry_name, arguments, confirm),
            self._loop,
        )
        return future.result(timeout=120)

    def _start_loop_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._ready.clear()

        def _run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def _stop_loop_thread(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5)

        self._loop = None
        self._thread = None

    async def _connect_async(self, config_path: Path) -> int:
        if not config_path.exists():
            return 0

        config = json.loads(config_path.read_text(encoding="utf-8"))
        servers = config.get("servers", [])

        for server in servers:
            name = server.get("name", "desconhecido")
            try:
                await self._connect_server(server)
            except Exception as exc:
                self._errors.append(f"{name}: {exc}")

        return len(self._tool_bindings)

    async def _connect_server(self, server: dict[str, Any]) -> None:
        name = server["name"]
        transport = server.get("transport", "stdio")
        stack = AsyncExitStack()

        if transport == "stdio":
            env = {**os.environ, **_resolve_env(server.get("env", {}))}
            params = StdioServerParameters(
                command=_resolve_command(server["command"]),
                args=server.get("args", []),
                env=env,
            )
            read, write = await stack.enter_async_context(stdio_client(params))
        elif transport in ("http", "streamable-http"):
            if streamable_http_client is None:
                raise RuntimeError("Transporte streamable-http indisponível.")
            read, write, _ = await stack.enter_async_context(
                streamable_http_client(server["url"])
            )
        elif transport == "sse":
            if sse_client is None:
                raise RuntimeError("Transporte SSE indisponível.")
            read, write = await stack.enter_async_context(sse_client(server["url"]))
        else:
            raise ValueError(f"Transporte não suportado: {transport}")

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        self._servers[name] = ServerConnection(name=name, session=session, stack=stack)

        tools_response = await session.list_tools()
        for tool in tools_response.tools:
            registry_name = f"{name}__{tool.name}"
            input_schema = tool.inputSchema or {"type": "object", "properties": {}}

            self._tool_bindings[registry_name] = McpToolBinding(
                registry_name=registry_name,
                server_name=name,
                tool_name=tool.name,
                description=tool.description or f"Tool MCP {tool.name}",
                input_schema=input_schema,
                needs_confirmation=_tool_needs_confirmation(tool.name),
            )

    async def _call_tool_async(
        self,
        registry_name: str,
        arguments: dict[str, Any],
        confirm,
    ) -> str:
        binding = self._tool_bindings.get(registry_name)
        if binding is None:
            return f"Erro: tool MCP desconhecida: {registry_name}"

        connection = self._servers.get(binding.server_name)
        if connection is None:
            return f"Erro: servidor MCP desconectado: {binding.server_name}"

        if binding.needs_confirmation:
            if confirm is None:
                return (
                    "Erro: esta operação exige confirmação, mas nenhum confirmador foi fornecido."
                )
            preview = (
                f"Servidor MCP: {binding.server_name}\n"
                f"Tool: {binding.tool_name}\n"
                f"Argumentos:\n{json.dumps(arguments, indent=2, ensure_ascii=False)}"
            )
            if not confirm(preview):
                return "Operação cancelada pelo usuário."

        result = await connection.session.call_tool(binding.tool_name, arguments=arguments)
        return _format_call_result(result)

    async def _disconnect_async(self) -> None:
        for connection in list(self._servers.values()):
            await connection.stack.aclose()