"""MCP server commands — serve and install."""

import json
import sys
from pathlib import Path

import click

from splunkctl import output
from splunkctl.mcp.transport import LOOPBACK_HOSTS, local_mcp_url


@click.group("mcp")
def mcp_group() -> None:
    """Built-in MCP server for agent integration."""


@mcp_group.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
    help="Transport type. 'http' runs streamable-HTTP.",
)
@click.option(
    "--host",
    type=click.Choice(LOOPBACK_HOSTS),
    default="127.0.0.1",
    show_default=True,
    help="Loopback address for HTTP transport (ignored for stdio).",
)
@click.option(
    "--port",
    type=int,
    default=8765,
    show_default=True,
    help="Port for HTTP transport (ignored for stdio).",
)
def mcp_serve(transport: str, host: str, port: int) -> None:
    """Start the MCP server.

    Default is stdio (standard MCP transport). HTTP is restricted to the
    local machine and does not provide authentication.
    """
    from splunkctl.mcp.server import run_server

    real_transport = "streamable-http" if transport == "http" else "stdio"
    run_server(transport=real_transport, host=host, port=port)


@mcp_group.command("install")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
    help="Transport for the generated config. 'http' writes a URL-based entry.",
)
@click.option(
    "--host",
    type=click.Choice(LOOPBACK_HOSTS),
    default="127.0.0.1",
    show_default=True,
    help="Loopback host for HTTP config (ignored for stdio).",
)
@click.option(
    "--port",
    type=int,
    default=8765,
    show_default=True,
    help="Port for HTTP config (ignored for stdio).",
)
def mcp_install(transport: str, host: str, port: int) -> None:
    """Write .mcp.json for Claude Code registration."""
    if transport == "http":
        server_entry: dict[str, object] = {
            "url": local_mcp_url(host, port),
        }
    else:
        exe = sys.executable
        server_entry = {
            "command": exe,
            "args": ["-m", "splunkctl", "mcp", "serve"],
        }

    config: dict[str, object] = {
        "mcpServers": {
            "splunkctl": server_entry,
        },
    }

    dest = Path.cwd() / ".mcp.json"
    if dest.exists():
        existing = json.loads(dest.read_text(encoding="utf-8"))
        if existing.get("mcpServers") is None:
            existing["mcpServers"] = {}
        existing.setdefault("mcpServers", {})["splunkctl"] = server_entry
        config = existing

    dest.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    output.info(f"Wrote MCP config to {dest}")
