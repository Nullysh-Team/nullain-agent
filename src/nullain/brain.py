from nullain import memory
from nullain.mcp_client import McpManager
from nullain.tools import init_tools, shutdown_tools


class Brain:
    def __init__(self) -> None:
        self.mcp_manager = McpManager()
        self.started = False

    def startup(self) -> tuple[int, int]:
        memory.init_db()
        mcp_count = self.mcp_manager.connect()
        total = init_tools(self.mcp_manager)
        self.started = True
        return total, mcp_count

    def shutdown(self) -> None:
        if not self.started:
            return
        self.mcp_manager.disconnect()
        shutdown_tools()
        self.started = False

    def reload_mcp(self) -> tuple[int, int]:
        self.mcp_manager.disconnect()
        self.mcp_manager = McpManager()
        mcp_count = self.mcp_manager.connect()
        total = init_tools(self.mcp_manager)
        return total, mcp_count

    @property
    def mcp_errors(self) -> list[str]:
        return self.mcp_manager.errors