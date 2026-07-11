"""Protocol-level tests for the MCP server.

Drives a real MCP client/server pair over in-memory streams — the same
code path a live stdio client exercises (initialize handshake, tools/list,
tools/call, notifications, resources). ``_exec_cli`` is patched so no
subprocess or network is involved; everything up to the CLI boundary runs
for real.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import anyio
import mcp.types as types
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from splunkctl.mcp.server import create_server


def _text(result: types.CallToolResult) -> str:
    parts = [c.text for c in result.content if isinstance(c, types.TextContent)]
    return "\n".join(parts)


@pytest.fixture
def captured_cli() -> Iterator[list[list[str]]]:
    """Patch _exec_cli, recording arg lists and returning canned output."""
    calls: list[list[str]] = []

    def fake_exec(args: list[str]) -> str:
        calls.append(args)
        return "[]"

    with patch("splunkctl.mcp.server._exec_cli", side_effect=fake_exec):
        yield calls


def test_focused_tool_call_reaches_cli(captured_cli: list[list[str]]) -> None:
    """A focused typed tool must execute, not die in arg validation."""

    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("focus", {"group": "indexes"})
            assert not res.isError, _text(res)
            res = await session.call_tool("indexes_list", {})
            assert not res.isError, _text(res)

    anyio.run(main)
    assert ["indexes", "list"] in captured_cli


def test_focused_tool_args_passthrough(captured_cli: list[list[str]]) -> None:
    """Positional and option arguments reach the CLI arg list intact."""

    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("focus", {"group": "search"})
            assert not res.isError, _text(res)
            res = await session.call_tool(
                "search_run", {"spl": "index=main", "limit": 5}
            )
            assert not res.isError, _text(res)

    anyio.run(main)
    run_calls = [c for c in captured_cli if c[:2] == ["search", "run"]]
    assert run_calls, f"search run never executed: {captured_cli}"
    args: list[Any] = run_calls[0]
    assert "index=main" in args
    assert "--limit" in args
    assert "5" in args


def test_capabilities_and_meta_tools() -> None:
    """Handshake declares listChanged + resources; 5 meta-tools listed."""

    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            caps = session.get_server_capabilities()
            assert caps is not None
            assert caps.tools is not None
            assert caps.tools.listChanged is True
            assert caps.resources is not None
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert names == {"help", "focus", "unfocus", "run", "usage"}

    anyio.run(main)


def test_focus_unfocus_lifecycle_with_notifications() -> None:
    """focus registers tools + notifies; unfocus removes them + notifies."""
    notifications: list[str] = []

    async def handler(message: Any) -> None:
        root = getattr(message, "root", None)
        method = getattr(root, "method", None)
        if method:
            notifications.append(method)

    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(
            server, message_handler=handler
        ) as session:
            await session.call_tool("focus", {"group": "indexes"})
            tools = {t.name for t in (await session.list_tools()).tools}
            assert "indexes_list" in tools
            assert "indexes_create" in tools

            res = await session.call_tool("unfocus", {"group": "indexes"})
            assert "Unloaded" in _text(res)
            tools = {t.name for t in (await session.list_tools()).tools}
            assert "indexes_list" not in tools

            await session.call_tool("focus", {"group": "indexes"})
            await session.call_tool("focus", {"group": "search"})
            res = await session.call_tool("unfocus", {})
            assert "all focused tools" in _text(res)
            tools = {t.name for t in (await session.list_tools()).tools}
            assert tools == {"help", "focus", "unfocus", "run", "usage"}

    anyio.run(main)
    assert notifications.count("notifications/tools/list_changed") >= 5


def test_usage_auto_registers_tool() -> None:
    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("usage", {"command": "indexes list"})
            payload = _text(res)
            assert '"inputSchema"' in payload
            assert '"indexes_list"' in payload
            tools = {t.name for t in (await session.list_tools()).tools}
            assert "indexes_list" in tools

    anyio.run(main)


def test_resources_listed_and_readable() -> None:
    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            resources = (await session.list_resources()).resources
            assert len(resources) > 10
            uris = [str(r.uri) for r in resources]
            assert all(u.startswith("guide://") for u in uris)
            content = await session.read_resource(resources[0].uri)
            first = content.contents[0]
            assert isinstance(first, types.TextResourceContents)
            assert len(first.text) > 100

    anyio.run(main)


def test_run_tool_executes_command(captured_cli: list[list[str]]) -> None:
    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("run", {"command": "indexes list"})
            assert not res.isError

    anyio.run(main)
    assert ["indexes", "list"] in captured_cli


def test_error_paths() -> None:
    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            res = await session.call_tool("nonexistent_tool", {})
            assert res.isError
            assert "Unknown tool" in _text(res)

            res = await session.call_tool("focus", {"group": "nope"})
            assert "No tools found" in _text(res)
            assert "Available:" in _text(res)

            res = await session.call_tool("usage", {"command": "bogus cmd"})
            assert "Unknown command" in _text(res)

    anyio.run(main)


def test_focused_tool_missing_required_arg_yields_cli_usage_error() -> None:
    """Bad args reach Click, which reports a usage error (real subprocess)."""

    async def main() -> None:
        server = create_server()
        async with create_connected_server_and_client_session(server) as session:
            await session.call_tool("focus", {"group": "search"})
            res = await session.call_tool("search_run", {})
            text = _text(res)
            assert "Missing argument" in text or "Usage" in text

    anyio.run(main)
