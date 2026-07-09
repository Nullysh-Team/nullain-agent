import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import Enum
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

logger = logging.getLogger("nullain.mcp")

CONFIG_PATH = Path("mcp.config.json")

# Tools com estes trechos no nome sempre exigem confirmação.
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
    "execute",
    "run",
    "send",
    "transfer",
    "deploy",
    "destroy",
    "drop",
    "insert",
    "mutate",
    "invoke",
    "call",
    "publish",
    "upload",
    "grant",
    "revoke",
)

# Apenas tools com nome claramente de leitura pulam confirmação.
# Qualquer tool fora desta allowlist exige confirmação (fail-closed).
SAFE_READ_KEYWORDS = (
    "list",
    "get",
    "read",
    "search",
    "find",
    "fetch",
    "query",
    "show",
    "describe",
    "status",
    "info",
    "help",
    "ping",
    "health",
    "count",
    "stat",
    "view",
    "inspect",
    "check",
    "lookup",
)

DEFAULT_TOOL_TIMEOUT = 30.0
HEALTH_CHECK_INTERVAL = 60.0
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0
RECONNECT_MAX_ATTEMPTS = 5


class ServerState(str, Enum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    DISABLED = "disabled"


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


@dataclass
class ServerStatus:
    name: str
    state: ServerState = ServerState.DISABLED
    last_error: str = ""
    tool_count: int = 0
    last_health_check: float = 0.0
    reconnect_attempts: int = 0


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
    """Fail-closed: só tools com nome claramente de leitura pulam confirmação.

    Write-like sempre confirmam. Nomes ambíguos (ex.: execute, transfer) também.
    """
    lower = tool_name.lower()
    if any(keyword in lower for keyword in WRITE_KEYWORDS):
        return True
    if any(keyword in lower for keyword in SAFE_READ_KEYWORDS):
        return False
    return True


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
        self._server_status: dict[str, ServerStatus] = {}
        self._server_configs: dict[str, dict[str, Any]] = {}
        self._health_task: asyncio.Task | None = None

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def get_tool_bindings(self) -> dict[str, McpToolBinding]:
        return dict(self._tool_bindings)

    def get_server_status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": status.name,
                "state": status.state.value,
                "last_error": status.last_error,
                "tool_count": status.tool_count,
                "reconnect_attempts": status.reconnect_attempts,
            }
            for status in self._server_status.values()
        ]

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
            self._start_health_check()
            return count
        except Exception as exc:
            self._errors.append(str(exc))
            return 0

    def disconnect(self) -> None:
        if not self._loop:
            return

        if self._connected:
            self._stop_health_check()
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
        self._server_status.clear()
        self._server_configs.clear()
        self._stop_loop_thread()

    def connect_server(self, server_config: dict[str, Any]) -> int:
        """Conecta um único servidor sem derrubar os outros (reload incremental)."""
        if not self._loop:
            self._start_loop_thread()

        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(
            self._connect_server_async(server_config),
            self._loop,
        )
        try:
            count = future.result(timeout=120)
            self._connected = True
            self._start_health_check()
            return count
        except Exception as exc:
            self._errors.append(str(exc))
            return 0

    def disconnect_server(self, name: str) -> None:
        if not self._loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self._disconnect_server_async(name),
            self._loop,
        )
        try:
            future.result(timeout=30)
        except Exception:
            pass

    def sync_from_config(self, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
        """Reload incremental: adiciona/remove/reconecta conforme mcp.config.json."""
        if not self._loop:
            self._start_loop_thread()
        assert self._loop is not None

        future = asyncio.run_coroutine_threadsafe(
            self._sync_from_config_async(config_path),
            self._loop,
        )
        try:
            result = future.result(timeout=180)
            self._connected = True
            self._start_health_check()
            return result
        except Exception as exc:
            self._errors.append(str(exc))
            return {
                "connected": [],
                "disconnected": [],
                "reconnected": [],
                "errors": [str(exc)],
                "tool_count": len(self._tool_bindings),
            }

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "servers": self.get_server_status(),
            "tool_count": len(self._tool_bindings),
            "errors": list(self._errors[-20:]),
        }

    async def call_tool_async(
        self,
        registry_name: str,
        arguments: dict[str, Any],
        confirm,
    ) -> str:
        """API async (FastAPI) — reusa o loop dedicado do MCP via threadsafe se preciso."""
        if not self._loop:
            return "Erro: MCP não conectado."
        if asyncio.get_running_loop() is self._loop:
            return await self._call_tool_async(registry_name, arguments, confirm)
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(registry_name, arguments, confirm),
            self._loop,
        )
        return await asyncio.wrap_future(future)

    def call_tool_sync(
        self,
        registry_name: str,
        arguments: dict[str, Any],
        confirm,
    ) -> str:
        if not self._loop:
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

    def _start_health_check(self) -> None:
        if not self._loop or self._health_task is not None:
            return

        async def _run_health_check() -> None:
            while self._connected:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                await self._health_check_all()

        future = asyncio.run_coroutine_threadsafe(
            self._health_check_all(),
            self._loop,
        )
        try:
            future.result(timeout=5)
        except Exception:
            pass

        if self._loop:
            self._health_task = self._loop.create_task(_run_health_check())

    def _stop_health_check(self) -> None:
        if self._health_task and self._loop:
            self._health_task.cancel()
            self._health_task = None

    async def _connect_async(self, config_path: Path) -> int:
        if not config_path.exists():
            return 0

        config = json.loads(config_path.read_text(encoding="utf-8"))
        servers = config.get("servers", [])

        for server in servers:
            name = server.get("name", "desconhecido")
            self._server_configs[name] = server
            try:
                await self._connect_server_async(server)
            except Exception as exc:
                self._errors.append(f"{name}: {exc}")

        return len(self._tool_bindings)

    async def _sync_from_config_async(self, config_path: Path) -> dict[str, Any]:
        desired: dict[str, dict[str, Any]] = {}
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            for server in config.get("servers", []):
                name = server.get("name")
                if name:
                    desired[name] = server

        connected: list[str] = []
        disconnected: list[str] = []
        reconnected: list[str] = []
        errors: list[str] = []

        current_names = set(self._server_configs.keys()) | set(self._servers.keys())
        for name in sorted(current_names - set(desired.keys())):
            try:
                await self._disconnect_server_async(name)
                self._server_configs.pop(name, None)
                disconnected.append(name)
            except Exception as exc:
                errors.append(f"disconnect {name}: {exc}")

        for name, server in desired.items():
            previous = self._server_configs.get(name)
            if previous == server and name in self._servers:
                status = self._server_status.get(name)
                if status and status.state == ServerState.CONNECTED:
                    continue
            try:
                was_connected = name in self._servers
                await self._connect_server_async(server)
                if was_connected:
                    reconnected.append(name)
                else:
                    connected.append(name)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            self._errors.extend(errors)

        return {
            "connected": connected,
            "disconnected": disconnected,
            "reconnected": reconnected,
            "errors": errors,
            "tool_count": len(self._tool_bindings),
        }

    async def _connect_server_async(self, server: dict[str, Any]) -> int:
        name = server["name"]
        self._server_configs[name] = server

        if name in self._servers:
            await self._disconnect_server_async(name)

        previous_attempts = 0
        if name in self._server_status:
            previous_attempts = self._server_status[name].reconnect_attempts

        self._server_status[name] = ServerStatus(
            name=name,
            state=ServerState.RECONNECTING,
            reconnect_attempts=previous_attempts,
        )

        try:
            connection = await self._establish_connection(server)
            self._servers[name] = connection

            tools_count = await self._register_tools(name, connection.session)
            self._server_status[name] = ServerStatus(
                name=name,
                state=ServerState.CONNECTED,
                tool_count=tools_count,
                reconnect_attempts=previous_attempts,
                last_health_check=time.time(),
            )
            return tools_count
        except Exception as exc:
            self._server_status[name] = ServerStatus(
                name=name,
                state=ServerState.DEGRADED,
                last_error=str(exc),
                reconnect_attempts=previous_attempts,
            )
            self._errors.append(f"{name}: {exc}")
            raise

    async def _establish_connection(self, server: dict[str, Any]) -> ServerConnection:
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

        return ServerConnection(name=name, session=session, stack=stack)

    async def _register_tools(self, server_name: str, session: ClientSession) -> int:
        tools_response = await session.list_tools()
        count = 0
        for tool in tools_response.tools:
            registry_name = f"{server_name}.{tool.name}"
            input_schema = tool.inputSchema or {"type": "object", "properties": {}}

            self._tool_bindings[registry_name] = McpToolBinding(
                registry_name=registry_name,
                server_name=server_name,
                tool_name=tool.name,
                description=tool.description or f"Tool MCP {tool.name}",
                input_schema=input_schema,
                needs_confirmation=_tool_needs_confirmation(tool.name),
            )
            count += 1
        return count

    async def _disconnect_server_async(self, name: str) -> None:
        connection = self._servers.pop(name, None)
        if connection:
            try:
                await connection.stack.aclose()
            except Exception:
                pass

        for key in list(self._tool_bindings):
            if self._tool_bindings[key].server_name == name:
                self._tool_bindings.pop(key, None)

        if name in self._server_status:
            self._server_status[name] = ServerStatus(
                name=name,
                state=ServerState.DISABLED,
                tool_count=0,
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

        status = self._server_status.get(binding.server_name)
        if status and status.state == ServerState.DISABLED:
            return f"Erro: servidor MCP desabilitado: {binding.server_name}"

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

        try:
            result = await asyncio.wait_for(
                connection.session.call_tool(binding.tool_name, arguments=arguments),
                timeout=DEFAULT_TOOL_TIMEOUT,
            )
            return _format_call_result(result)
        except asyncio.TimeoutError:
            self._set_degraded(binding.server_name, f"Timeout na tool {binding.tool_name}")
            return f"Erro: tool MCP excedeu o timeout de {DEFAULT_TOOL_TIMEOUT}s."
        except Exception as exc:
            self._set_degraded(binding.server_name, str(exc))
            await self._schedule_reconnect(binding.server_name)
            return f"Erro ao chamar tool MCP: {exc}"

    def _set_degraded(self, server_name: str, error: str) -> None:
        status = self._server_status.get(server_name)
        if status:
            status.state = ServerState.DEGRADED
            status.last_error = error

    async def _schedule_reconnect(self, server_name: str) -> None:
        if not self._loop:
            return

        status = self._server_status.get(server_name)
        if not status or status.state == ServerState.DISABLED:
            return

        status.state = ServerState.RECONNECTING
        status.reconnect_attempts += 1

        if status.reconnect_attempts > RECONNECT_MAX_ATTEMPTS:
            status.state = ServerState.DISABLED
            status.last_error = "Máximo de tentativas de reconexão excedido."
            return

        delay = min(
            RECONNECT_BASE_DELAY * (2 ** (status.reconnect_attempts - 1)),
            RECONNECT_MAX_DELAY,
        )

        config = self._server_configs.get(server_name)
        if config:
            await asyncio.sleep(delay)
            try:
                await self._connect_server_async(config)
            except Exception as exc:
                status.state = ServerState.DEGRADED
                status.last_error = f"Reconexão falhou (tentativa {status.reconnect_attempts}): {exc}"

    async def _health_check_all(self) -> None:
        for name in list(self._servers):
            await self._health_check_server(name)

    async def _health_check_server(self, name: str) -> None:
        connection = self._servers.get(name)
        if not connection:
            return

        status = self._server_status.get(name)
        if not status:
            return

        try:
            await asyncio.wait_for(
                connection.session.list_tools(),
                timeout=10,
            )
            status.state = ServerState.CONNECTED
            status.last_error = ""
            status.last_health_check = time.time()
        except Exception as exc:
            self._set_degraded(name, str(exc))
            await self._schedule_reconnect(name)

    async def _disconnect_async(self) -> None:
        for connection in list(self._servers.values()):
            try:
                await connection.stack.aclose()
            except Exception:
                pass