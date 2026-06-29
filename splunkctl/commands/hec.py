"""HEC (HTTP Event Collector) token management via SDK."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


@click.group("hec")
def hec_group() -> None:
    """Manage HTTP Event Collector tokens."""


@hec_group.command("list")
@click.pass_context
def list_hec(ctx: click.Context) -> None:
    """List HEC tokens."""
    client = get_client(ctx)
    items = client.service.hec_tokens.list()
    rows: list[dict[str, Any]] = [
        {
            "name": t.name,
            "token": t.content.get("token", ""),
            "index": t.content.get("index", ""),
            "disabled": t.content.get("disabled", ""),
            "sourcetype": t.content.get("sourcetype", ""),
        }
        for t in items
    ]
    if not rows:
        output.info("No HEC tokens found.")
        return
    output.render(ctx, rows)


@hec_group.command("get")
@click.argument("name")
@click.pass_context
def get_hec(ctx: click.Context, name: str) -> None:
    """Get HEC token details."""
    client = get_client(ctx)
    try:
        token = client.service.hec_tokens[name]
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    row: dict[str, Any] = {
        "name": token.name,
        "token": token.content.get("token", ""),
        "index": token.content.get("index", ""),
        "indexes": token.content.get("indexes", ""),
        "sourcetype": token.content.get("sourcetype", ""),
        "disabled": token.content.get("disabled", ""),
        "useACK": token.content.get("useACK", ""),
    }
    output.render(ctx, row)


@hec_group.command("create")
@click.option("--name", required=True, help="Token name.")
@click.option("--index", default=None, help="Default index.")
@click.option("--indexes", default=None, help="Allowed indexes (comma-separated).")
@click.option("--sourcetype", default=None, help="Default source type.")
@click.pass_context
def create_hec(
    ctx: click.Context,
    name: str,
    *,
    index: str | None,
    indexes: str | None,
    sourcetype: str | None,
) -> None:
    """Create a new HEC token."""
    details = f"  name: {name}"
    if index:
        details += f"\n  index: {index}"
    if not guard.check(ctx, f"Create HEC token '{name}'", details=details):
        return
    client = get_client(ctx)
    kwargs: dict[str, str] = {}
    if index:
        kwargs["index"] = index
    if indexes:
        kwargs["indexes"] = indexes
    if sourcetype:
        kwargs["sourcetype"] = sourcetype
    try:
        client.service.hec_tokens.create(name, **kwargs)
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' created.")


@hec_group.command("delete")
@click.argument("name")
@click.pass_context
def delete_hec(ctx: click.Context, name: str) -> None:
    """Delete a HEC token."""
    if not guard.check(ctx, f"Delete HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].delete()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    except Exception as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' deleted.")


@hec_group.command("enable")
@click.argument("name")
@click.pass_context
def enable_hec(ctx: click.Context, name: str) -> None:
    """Enable a HEC token."""
    if not guard.check(ctx, f"Enable HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].enable()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' enabled.")


@hec_group.command("disable")
@click.argument("name")
@click.pass_context
def disable_hec(ctx: click.Context, name: str) -> None:
    """Disable a HEC token."""
    if not guard.check(ctx, f"Disable HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].disable()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' disabled.")
