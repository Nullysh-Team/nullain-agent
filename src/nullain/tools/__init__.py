import json
import warnings
from collections.abc import Callable
from typing import Any

from nullain.tools import files, shell

ConfirmFn = Callable[[str], bool]

ToolFn = Callable[..., str]

NATIVE_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "list_files": {
        "needs_confirmation": False,
        "source": "native",
        "fn": files.list_files,
        "schema": {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "Lista arquivos e pastas em um diretório.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Caminho do diretório. Padrão: diretório atual.",
                        }
                    },
                    "required": [],
                },
            },
        },
    },
    "read_file": {
        "needs_confirmation": False,
        "source": "native",
        "fn": files.read_file,
        "schema": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Lê o conteúdo de um arquivo de texto.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Caminho do arquivo.",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
    },
    "write_file": {
        "needs_confirmation": True,
        "source": "native",
        "fn": files.write_file,
        "schema": {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Grava conteúdo em um arquivo de texto.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Caminho do arquivo.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Conteúdo a gravar.",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
    },
    "run_command": {
        "needs_confirmation": True,
        "source": "native",
        "fn": shell.run_command,
        "schema": {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": (
                    "Executa um comando no shell do sistema. "
                    "Sempre requer confirmação do usuário antes de rodar. "
                    "No Windows, use PowerShell ou cmd — nunca comandos Unix."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {
                            "type": "string",
                            "description": "Comando shell a executar.",
                        }
                    },
                    "required": ["cmd"],
                },
            },
        },
    },
}

TOOL_REGISTRY: dict[str, dict[str, Any]] = dict(NATIVE_TOOL_REGISTRY)

_mcp_manager = None


class ToolRegistry:
    def __init__(
        self,
        tools: dict[str, dict[str, Any]],
        *,
        mcp_manager: Any | None = None,
        confirm_all: bool = False,
    ) -> None:
        self._tools = tools
        self._mcp_manager = mcp_manager
        self.confirm_all = confirm_all

    def get(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def schemas(self) -> list[dict[str, Any]]:
        return [entry["schema"] for entry in self._tools.values()]

    def _confirmation_preview(self, name: str, arguments: dict[str, Any]) -> str:
        return f"Tool: {name}\nArgumentos:\n{json.dumps(arguments, indent=2, ensure_ascii=False)}"

    def _enforce_extra_confirmation(
        self,
        name: str,
        arguments: dict[str, Any],
        confirm: ConfirmFn | None,
    ) -> str | None:
        if confirm is None:
            return "Erro: esta operação exige confirmação, mas nenhum confirmador foi fornecido."
        if not confirm(self._confirmation_preview(name, arguments)):
            return "Operação cancelada pelo usuário."
        return None

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        confirm: ConfirmFn | None = None,
    ) -> str:
        parse_error = arguments.get("__parse_error__")
        if isinstance(parse_error, str):
            return parse_error

        entry = self._tools.get(name)
        if entry is None:
            return f"Erro: tool desconhecida: {name}"

        native_needs_confirmation = bool(entry.get("needs_confirmation"))

        if entry.get("source") == "mcp":
            if self._mcp_manager is None:
                return "Erro: MCP não conectado."
            if self.confirm_all and not native_needs_confirmation:
                blocked = self._enforce_extra_confirmation(name, arguments, confirm)
                if blocked is not None:
                    return blocked
            return self._mcp_manager.call_tool_sync(name, arguments, confirm)

        fn: ToolFn = entry["fn"]

        try:
            if self.confirm_all and not native_needs_confirmation:
                blocked = self._enforce_extra_confirmation(name, arguments, confirm)
                if blocked is not None:
                    return blocked
            if native_needs_confirmation or entry.get("source") in {
                "skill",
                "squad",
                "loop",
                "coding",
            }:
                try:
                    return fn(**arguments, confirm=confirm)
                except TypeError:
                    return fn(**arguments)
            return fn(**arguments)
        except TypeError as exc:
            return f"Erro: argumentos inválidos para {name}: {exc}"
        except Exception as exc:
            return f"Erro ao executar {name}: {exc}"


def init_tools(mcp_manager=None) -> int:
    """Monta TOOL_REGISTRY: nativas + skills + squads + loop + coding + MCP."""
    global _mcp_manager, TOOL_REGISTRY

    _mcp_manager = mcp_manager
    TOOL_REGISTRY = dict(NATIVE_TOOL_REGISTRY)

    try:
        from nullain.skills.registry import build_skill_tools, get_skill_registry

        get_skill_registry()  # garante load
        TOOL_REGISTRY.update(build_skill_tools())
    except Exception:
        pass

    try:
        from nullain.squads.orchestrator import build_squad_tools

        TOOL_REGISTRY.update(build_squad_tools())
    except Exception:
        pass

    try:
        from nullain.loop.engine import build_loop_tools

        TOOL_REGISTRY.update(build_loop_tools())
    except Exception:
        pass

    try:
        from nullain.coding.harness import build_coding_tools

        TOOL_REGISTRY.update(build_coding_tools())
    except Exception:
        pass

    if mcp_manager is not None:
        for name, binding in mcp_manager.get_tool_bindings().items():
            TOOL_REGISTRY[name] = {
                "needs_confirmation": binding.needs_confirmation,
                "source": "mcp",
                "schema": {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"[MCP:{binding.server_name}] {binding.description}",
                        "parameters": binding.input_schema,
                    },
                },
            }

    return len(TOOL_REGISTRY)


def shutdown_tools() -> None:
    global _mcp_manager, TOOL_REGISTRY
    _mcp_manager = None
    TOOL_REGISTRY = dict(NATIVE_TOOL_REGISTRY)


def default_registry() -> ToolRegistry:
    return ToolRegistry(dict(TOOL_REGISTRY), mcp_manager=_mcp_manager)


def restricted(names: list[str]) -> ToolRegistry:
    subset: dict[str, dict[str, Any]] = {}
    for name in names:
        if name in TOOL_REGISTRY:
            subset[name] = TOOL_REGISTRY[name]
        else:
            warnings.warn(f"Tool ignorada no registry restrito: {name}", stacklevel=2)
    return ToolRegistry(subset, mcp_manager=_mcp_manager)


def get_tool_schemas() -> list[dict[str, Any]]:
    return default_registry().schemas()


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    confirm: ConfirmFn | None = None,
) -> str:
    return default_registry().execute(name, arguments, confirm)


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return {"__parse_error__": f"Erro: argumentos JSON inválidos: {exc}"}
