"""Política fail-closed de confirmação para tools MCP."""

from nullain.mcp_client import _tool_needs_confirmation


def test_write_like_always_needs_confirmation():
    assert _tool_needs_confirmation("write_file") is True
    assert _tool_needs_confirmation("create_issue") is True
    assert _tool_needs_confirmation("delete_repo") is True
    assert _tool_needs_confirmation("execute_script") is True
    assert _tool_needs_confirmation("run_pipeline") is True
    assert _tool_needs_confirmation("send_email") is True
    assert _tool_needs_confirmation("transfer_funds") is True


def test_safe_read_skips_confirmation():
    assert _tool_needs_confirmation("list_files") is False
    assert _tool_needs_confirmation("get_issue") is False
    assert _tool_needs_confirmation("search_code") is False
    assert _tool_needs_confirmation("read_resource") is False
    assert _tool_needs_confirmation("fetch_status") is False
    assert _tool_needs_confirmation("health_check") is False


def test_ambiguous_names_fail_closed():
    assert _tool_needs_confirmation("do_stuff") is True
    assert _tool_needs_confirmation("process") is True
    assert _tool_needs_confirmation("handle_request") is True
    assert _tool_needs_confirmation("sync") is True
