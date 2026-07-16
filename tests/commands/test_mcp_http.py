"""Tests for MCP streamable-HTTP transport support."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

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


def test_mcp_serve_http_custom_host_port() -> None:
    """Custom --host and --port are forwarded."""
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
                "0.0.0.0",  # noqa: S104
                "--port",
                "9999",
            ],
        )
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        transport="streamable-http",
        host="0.0.0.0",  # noqa: S104
        port=9999,
    )


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
    mock_create.assert_called_once_with(host="127.0.0.1", port=8765)
    mock_server.run.assert_called_once_with(transport="stdio")


def test_run_server_http_calls_run_with_host_port() -> None:
    """run_server with streamable-http passes host/port to create_server."""
    mock_server = MagicMock()
    with (
        patch(
            "splunkctl.mcp.server.create_server", return_value=mock_server
        ) as mock_create,
        patch("splunkctl.mcp.server.sweep_spill_dir"),
    ):
        from splunkctl.mcp.server import run_server

        run_server(transport="streamable-http", host="0.0.0.0", port=9000)  # noqa: S104
    mock_create.assert_called_once_with(
        host="0.0.0.0",  # noqa: S104
        port=9000,
    )
    mock_server.run.assert_called_once_with(transport="streamable-http")


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
    """Custom host/port reflected in the URL."""
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
                "10.0.0.5",
                "--port",
                "4000",
            ],
        )
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    server = config["mcpServers"]["splunkctl"]
    assert server["url"] == "http://10.0.0.5:4000/mcp"


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
