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
