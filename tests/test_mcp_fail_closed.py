import asyncio
from unittest.mock import AsyncMock, MagicMock

from nullain.mcp_client import McpManager, McpToolBinding, ServerConnection


def test_mcp_write_tool_without_confirm_does_not_call_server():
    manager = McpManager()
    mock_session = MagicMock()
    mock_session.call_tool = AsyncMock()

    binding = McpToolBinding(
        registry_name="test__write_file",
        server_name="test",
        tool_name="write_file",
        description="write test",
        input_schema={"type": "object", "properties": {}},
        needs_confirmation=True,
    )
    manager._tool_bindings["test__write_file"] = binding
    manager._servers["test"] = ServerConnection(
        name="test",
        session=mock_session,
        stack=MagicMock(),
    )

    result = asyncio.run(
        manager._call_tool_async("test__write_file", {"path": "x"}, None)
    )

    assert "nenhum confirmador foi fornecido" in result
    mock_session.call_tool.assert_not_called()