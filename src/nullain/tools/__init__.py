import json
from collections.abc import Callable
from typing import Any

from nullain.tools import files, shell

ConfirmFn = Callable[[str], bool]

ToolFn = Callable[..., str]

NATIVE_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "list_files": {
        "needs_confirmation": False,
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


def init_tools(mcp_manager=None) -> int:
    global _mcp_manager, TOOL_REGISTRY

    _mcp_manager = mcp_manager
    TOOL_REGISTRY = dict(NATIVE_TOOL_REGISTRY)

    if mcp_manager is None:
        return len(TOOL_REGISTRY)

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


def get_tool_schemas() -> list[dict[str, Any]]:
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    confirm: ConfirmFn | None = None,
) -> str:
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return f"Erro: tool desconhecida: {name}"

    if entry.get("source") == "mcp":
        if _mcp_manager is None:
            return "Erro: MCP não conectado."
        return _mcp_manager.call_tool_sync(name, arguments, confirm)

    fn: ToolFn = entry["fn"]

    try:
        if entry["needs_confirmation"]:
            return fn(**arguments, confirm=confirm)
        return fn(**arguments)
    except TypeError as exc:
        return f"Erro: argumentos inválidos para {name}: {exc}"
    except Exception as exc:
        return f"Erro ao executar {name}: {exc}"


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    return json.loads(raw_arguments)