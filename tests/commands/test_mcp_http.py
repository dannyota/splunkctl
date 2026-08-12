"""Tests for MCP streamable-HTTP transport support."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from mcp.server.mcpserver import MCPServer

from splunkctl.main import cli


def test_mcp_serve_default_transport() -> None:
    """Default transport is stdio — no flags needed."""
    runner = CliRunner()
    with patch("splunkctl.mcp.server.run_server") as mock_run:
        runner.invoke(cli, ["mcp", "serve"])
    mock_run.assert_called_once_with(transport="stdio", host="127.0.0.1", port=8765)


def test_mcp_serve_http_transport() -> None:
    """--transport http passes streamable-http to run_server."""
    runner = CliRunner()
    with patch("splunkctl.mcp.server.run_server") as mock_run:
        result = runner.invoke(cli, ["mcp", "serve", "--transport", "http"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        transport="streamable-http", host="127.0.0.1", port=8765
    )


def test_mcp_serve_http_localhost_custom_port() -> None:
    """A loopback hostname and custom port are forwarded."""
    runner = CliRunner()
    with patch("splunkctl.mcp.server.run_server") as mock_run:
        result = runner.invoke(
            cli,
            [
                "mcp",
                "serve",
                "--transport",
                "http",
                "--host",
                "localhost",
                "--port",
                "9999",
            ],
        )
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        transport="streamable-http",
        host="localhost",
        port=9999,
    )


def test_mcp_serve_rejects_non_loopback_host() -> None:
    """The CLI must not expose the unauthenticated MCP server remotely."""
    runner = CliRunner()
    with patch("splunkctl.mcp.server.run_server") as mock_run:
        result = runner.invoke(
            cli,
            [
                "mcp",
                "serve",
                "--transport",
                "http",
                "--host",
                "0.0.0.0",  # noqa: S104 - verifies unsafe bind is rejected
            ],
        )
    assert result.exit_code != 0
    assert "127.0.0.1" in result.output
    mock_run.assert_not_called()


def test_mcp_serve_invalid_transport() -> None:
    """Invalid transport value is rejected by Click."""
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "serve", "--transport", "grpc"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "invalid choice" in result.output.lower()


def test_mcp_serve_help_shows_transport() -> None:
    """Help text documents transport options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "stdio" in result.output
    assert "http" in result.output


def test_run_server_stdio_calls_run() -> None:
    """run_server with stdio calls server.run(transport='stdio')."""
    from splunkctl.mcp.server import run_server

    mock_server = MagicMock()
    with (
        patch(
            "splunkctl.mcp.server.create_server", return_value=mock_server
        ) as mock_create,
        patch("splunkctl.mcp.server.sweep_spill_dir"),
    ):
        run_server(transport="stdio")
    mock_create.assert_called_once_with()
    mock_server.run.assert_called_once_with(transport="stdio")


def test_run_server_http_passes_host_port_to_transport() -> None:
    """MCP 2 receives HTTP settings at run(), not construction."""
    mock_server = MagicMock()
    with (
        patch(
            "splunkctl.mcp.server.create_server", return_value=mock_server
        ) as mock_create,
        patch("splunkctl.mcp.server.sweep_spill_dir"),
    ):
        from splunkctl.mcp.server import run_server

        run_server(transport="streamable-http", host="localhost", port=9000)
    mock_create.assert_called_once_with()
    mock_server.run.assert_called_once_with(
        transport="streamable-http",
        host="localhost",
        port=9000,
    )


def test_run_server_rejects_non_loopback_host() -> None:
    """Direct Python callers cannot bypass the local HTTP boundary."""
    from splunkctl.mcp.server import run_server

    with pytest.raises(ValueError, match="loopback"):
        run_server(transport="streamable-http", host="192.168.1.10", port=8765)


def test_created_server_rejects_direct_non_loopback_http() -> None:
    """The server object itself must enforce the local HTTP boundary."""
    from splunkctl.mcp.server import create_server

    server = create_server()
    with patch.object(
        MCPServer,
        "run_streamable_http_async",
        new_callable=AsyncMock,
    ) as parent_run:
        with pytest.raises(ValueError, match="loopback"):
            asyncio.run(
                server.run_streamable_http_async(
                    host="0.0.0.0",  # noqa: S104 - verifies unsafe bind is rejected
                )
            )
    parent_run.assert_not_awaited()


def test_mcp_install_stdio_default(tmp_path: Path) -> None:
    """Default install writes stdio (command+args) config."""
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(cli, ["mcp", "install"])
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    server = config["mcpServers"]["splunkctl"]
    assert "command" in server
    assert "serve" in server["args"]
    assert "url" not in server


def test_mcp_install_http_writes_url(tmp_path: Path) -> None:
    """--transport http writes a URL-based entry."""
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(cli, ["mcp", "install", "--transport", "http"])
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    server = config["mcpServers"]["splunkctl"]
    assert server["url"] == "http://127.0.0.1:8765/mcp"
    assert "command" not in server


def test_mcp_install_http_custom_host_port(tmp_path: Path) -> None:
    """A custom loopback host and port are reflected in the URL."""
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(
            cli,
            [
                "mcp",
                "install",
                "--transport",
                "http",
                "--host",
                "localhost",
                "--port",
                "4000",
            ],
        )
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    server = config["mcpServers"]["splunkctl"]
    assert server["url"] == "http://localhost:4000/mcp"


def test_mcp_install_http_formats_ipv6_loopback(tmp_path: Path) -> None:
    """IPv6 loopback URLs must contain brackets around the address."""
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(
            cli,
            ["mcp", "install", "--transport", "http", "--host", "::1"],
        )
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert config["mcpServers"]["splunkctl"]["url"] == "http://[::1]:8765/mcp"


def test_mcp_install_rejects_non_loopback_host(tmp_path: Path) -> None:
    """Generated configs cannot point at a non-loopback HTTP listener."""
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(
            cli,
            ["mcp", "install", "--transport", "http", "--host", "10.0.0.5"],
        )
    assert result.exit_code != 0
    assert not (tmp_path / ".mcp.json").exists()


def test_mcp_install_http_merges_existing(tmp_path: Path) -> None:
    """HTTP install merges into existing .mcp.json."""
    existing = {"mcpServers": {"other": {"command": "other-tool"}}}
    (tmp_path / ".mcp.json").write_text(json.dumps(existing))
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(cli, ["mcp", "install", "--transport", "http"])
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert "other" in config["mcpServers"]
    assert config["mcpServers"]["splunkctl"]["url"] == "http://127.0.0.1:8765/mcp"
