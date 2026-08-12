"""Tests for the MCP 2 dynamic CLI-tool registry."""

from __future__ import annotations

import asyncio

from mcp.types import TextContent

from splunkctl.main import cli
from splunkctl.mcp.dynamic_server import SplunkMCPServer
from splunkctl.mcp.tools import build_tool_index


def test_dynamic_tool_is_listed_with_click_schema() -> None:
    """A focused CLI tool must expose its Click-derived schema."""
    server = SplunkMCPServer("test")
    entry = build_tool_index(cli)["search_run"]

    server.add_cli_tool(entry, lambda _args: "[]")

    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "search_run")
    assert tool.input_schema == entry.schema


def test_dynamic_tool_call_builds_cli_arguments() -> None:
    """A dynamic MCP call must dispatch the expected CLI argument list."""
    calls: list[list[str]] = []
    server = SplunkMCPServer("test")
    entry = build_tool_index(cli)["search_run"]

    def execute(args: list[str]) -> str:
        calls.append(args)
        return "[]"

    server.add_cli_tool(entry, execute)

    result = asyncio.run(
        server.call_tool("search_run", {"spl": "index=main", "limit": 5})
    )

    assert result.is_error is False
    assert calls == [["search", "run", "--limit", "5", "index=main"]]
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "[]"


def test_removed_dynamic_tool_is_no_longer_listed() -> None:
    """Removing a focused tool must remove it from tools/list."""
    server = SplunkMCPServer("test")
    entry = build_tool_index(cli)["indexes_list"]
    server.add_cli_tool(entry, lambda _args: "[]")

    server.remove_cli_tool("indexes_list")

    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "indexes_list" not in names
