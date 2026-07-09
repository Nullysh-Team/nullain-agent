from nullain import memory
from nullain.mcp_client import McpManager
from nullain.skills import init_skills, reload_skills
from nullain.tools import init_tools, shutdown_tools
from nullain.workspace import set_workspace_root


class Brain:
    def __init__(self) -> None:
        self.mcp_manager = McpManager()
        self.started = False

    def startup(self) -> tuple[int, int]:
        set_workspace_root()
        memory.init_db()
        skill_registry = init_skills()
        self._last_skill_count = len(skill_registry.names())
        mcp_count = self.mcp_manager.connect()
        total = init_tools(self.mcp_manager)
        self.started = True
        return total, mcp_count

    def shutdown(self) -> None:
        if not self.started:
            return
        self.mcp_manager.disconnect()
        shutdown_tools()
        memory.stop_background_writer()
        self.started = False

    def refresh_tools(self) -> int:
        """Reconstroi TOOL_REGISTRY a partir de nativas + skills + squads + MCP."""
        return init_tools(self.mcp_manager)

    def reload_skills(self) -> dict:
        count = reload_skills()
        tools = self.refresh_tools()
        return {"skills": count, "tools": tools}

    def reload_mcp(self) -> tuple[int, int]:
        """Full reconnect (legado). Prefira reload_mcp_incremental."""
        self.mcp_manager.disconnect()
        self.mcp_manager = McpManager()
        mcp_count = self.mcp_manager.connect()
        total = init_tools(self.mcp_manager)
        return total, mcp_count

    def reload_mcp_incremental(self) -> dict:
        result = self.mcp_manager.sync_from_config()
        result["tools"] = self.refresh_tools()
        return result

    def add_mcp_server(self, server_config: dict) -> int:
        count = self.mcp_manager.connect_server(server_config)
        self.refresh_tools()
        return count

    def remove_mcp_server(self, name: str) -> None:
        self.mcp_manager.disconnect_server(name)
        self.refresh_tools()

    @property
    def mcp_errors(self) -> list[str]:
        return self.mcp_manager.errors

    @property
    def mcp_server_status(self) -> list[dict]:
        return self.mcp_manager.get_server_status()

    @property
    def skill_count(self) -> int:
        from nullain.skills import get_skill_registry

        return len(get_skill_registry().names())
