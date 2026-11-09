"""Read-only MCP discovery and subprocess policy."""

import asyncio
from subprocess import CompletedProcess
from unittest.mock import patch

from mcp.types import TextContent

from splunkctl.mcp.runner import exec_cli
from splunkctl.mcp.server import create_server


def text(result):
    return "\n".join(c.text for c in result.content if isinstance(c, TextContent))


def test_read_only_focus_hides_mutations():
    server = create_server(read_only=True)
    result = asyncio.run(server.call_tool("focus", {"group": "indexes"}))
    assert "indexes_list" in text(result)
    assert "indexes_create" not in text(result)
    result = asyncio.run(server.call_tool("usage", {"command": "indexes create"}))
    assert "Unknown command" in text(result)


def test_read_only_run_refuses_mutations_before_subprocess():
    server = create_server(read_only=True)
    for command in (
        "indexes create sc_test",
        "--profile example indexes create sc_test",
        "auth login",
        "auth logout",
    ):
        with patch("splunkctl.mcp.server._exec_cli") as execute:
            result = asyncio.run(server.call_tool("run", {"command": command}))
        execute.assert_not_called()
        assert "read-only:" in text(result)


def test_read_only_run_forces_subprocess_policy():
    server = create_server(read_only=True)
    with patch("splunkctl.mcp.server._exec_cli", return_value="[]") as execute:
        asyncio.run(server.call_tool("run", {"command": "indexes list"}))
    execute.assert_called_once_with(["indexes", "list"], read_only=True)


def test_exec_cli_read_only_forces_flag():
    with patch(
        "splunkctl.mcp.runner.subprocess.run",
        return_value=CompletedProcess([], 0, b"[]", b""),
    ) as run:
        assert exec_cli(["indexes", "list"], read_only=True) == "[]"
    assert "--read-only" in run.call_args.args[0]


def test_env_read_only_cannot_be_disabled(monkeypatch):
    monkeypatch.setenv("SPLUNKCTL_READ_ONLY", "yes")
    server = create_server(read_only=False)
    result = asyncio.run(server.call_tool("usage", {"command": "indexes create"}))
    assert "Unknown command" in text(result)


def test_read_only_typed_tool_forces_policy():
    server = create_server(read_only=True)
    asyncio.run(server.call_tool("focus", {"group": "indexes"}))
    with patch("splunkctl.mcp.server._exec_cli", return_value="[]") as execute:
        asyncio.run(server.call_tool("indexes_list", {}))
    execute.assert_called_once_with(["indexes", "list"], read_only=True)


def test_read_only_help_hides_mutations():
    server = create_server(read_only=True)
    result = asyncio.run(server.call_tool("help", {"group": "indexes"}))
    assert "indexes_list" in text(result)
    assert "indexes_create" not in text(result)


def test_mcp_serve_read_only_option():
    from click.testing import CliRunner

    from splunkctl.main import cli

    for args in (
        ["mcp", "serve", "--read-only"],
        ["--read-only", "mcp", "serve"],
    ):
        with patch("splunkctl.mcp.server.run_server") as run:
            result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert run.call_args.kwargs["read_only"] is True


def test_read_only_run_resolves_options_and_nested_groups():
    server = create_server(read_only=True)
    for command in (
        "--config unused.yml soar containers delete 1",
        "soar containers delete 1 --profile example",
        "api post server/info",
    ):
        with patch("splunkctl.mcp.server._exec_cli") as execute:
            result = asyncio.run(server.call_tool("run", {"command": command}))
        execute.assert_not_called()
        assert "read-only:" in text(result)
