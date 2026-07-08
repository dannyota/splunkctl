"""MCP server commands — serve and install."""

import json
import sys
from pathlib import Path

import click

from splunkctl import output


@click.group("mcp")
def mcp_group() -> None:
    """Built-in MCP server for agent integration."""


@mcp_group.command("serve")
def mcp_serve() -> None:
    """Start the MCP server on stdio."""
    from splunkctl.mcp.server import run_server

    run_server()


@mcp_group.command("install")
def mcp_install() -> None:
    """Write .mcp.json for Claude Code registration."""
    exe = sys.executable
    config = {
        "mcpServers": {
            "splunkctl": {
                "command": exe,
                "args": ["-m", "splunkctl", "mcp", "serve"],
            },
        },
    }

    dest = Path.cwd() / ".mcp.json"
    if dest.exists():
        existing = json.loads(dest.read_text(encoding="utf-8"))
        existing.setdefault("mcpServers", {})["splunkctl"] = config["mcpServers"][
            "splunkctl"
        ]
        config = existing

    dest.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    output.info(f"Wrote MCP config to {dest}")
