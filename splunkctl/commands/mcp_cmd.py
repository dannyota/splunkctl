"""MCP server commands — serve and install."""

from pathlib import Path

import click

from splunkctl import output
from splunkctl.mcp.transport import LOOPBACK_HOSTS


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
@click.option(
    "--read-only", is_flag=True, help="Refuse server mutations in every tool."
)
def mcp_serve(transport: str, host: str, port: int, read_only: bool) -> None:
    """Start the MCP server.

    Default is stdio (standard MCP transport). HTTP is restricted to the
    local machine and does not provide authentication.
    """
    from splunkctl.mcp.server import run_server

    real_transport = "streamable-http" if transport == "http" else "stdio"
    from splunkctl.mcp.policy import enabled

    if enabled(read_only):
        run_server(transport=real_transport, host=host, port=port, read_only=True)
    else:
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
@click.option(
    "--client",
    type=click.Choice(["claude", "codex", "cursor", "gemini"]),
    default="claude",
    show_default=True,
)
@click.option(
    "--preview", is_flag=True, help="Show registration changes without writing."
)
@click.option(
    "--read-only",
    is_flag=True,
    help="Register stdio with server mutations disabled.",
)
def mcp_install(
    transport: str, host: str, port: int, client: str, preview: bool, read_only: bool
) -> None:
    """Register splunkctl in this project's MCP configuration."""
    from splunkctl.mcp.install import install
    from splunkctl.mcp.policy import enabled

    dest, changed, entry = install(
        Path.cwd(),
        client=client,
        transport=transport,
        host=host,
        port=port,
        preview=preview,
        read_only=enabled(read_only),
    )
    if preview:
        output.render(
            click.get_current_context(),
            {"path": str(dest), "changed": changed, "entry": entry},
        )
    else:
        output.info(f"{'Wrote' if changed else 'Unchanged'} MCP config at {dest}")
