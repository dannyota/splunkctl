"""Server operations — system messages, license pools, KV store status."""

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


@click.group("server")
def server_group() -> None:
    """Server operations — messages, license, KV store."""


@server_group.command("messages")
@click.option("--dismiss", default=None, help="Delete a message by name.")
@click.pass_context
def messages(ctx: click.Context, dismiss: str | None) -> None:
    """List system messages, or dismiss one with --dismiss NAME --yes."""
    client = get_client(ctx)
    svc = client.service

    if dismiss is not None:
        if not guard.check(ctx, f"Dismiss system message '{dismiss}'"):
            return
        try:
            msg = svc.messages[dismiss]
        except KeyError:
            output.error(f"Message '{dismiss}' not found.")
            ctx.exit(1)
            return
        msg.delete()
        output.info(f"Message '{dismiss}' dismissed.")
        return

    rows: list[dict[str, Any]] = []
    for msg in svc.messages.list():
        c: dict[str, Any] = msg.content
        rows.append(
            {
                "name": msg.name,
                "severity": c.get("severity", ""),
                "message": c.get("message", ""),
                "time_created": c.get("timeCreated_iso", c.get("timeCreated", "")),
            }
        )
    output.render(ctx, rows, empty="No system messages.")


@server_group.command("license")
@click.pass_context
def license_pools(ctx: click.Context) -> None:
    """Show license pool usage."""
    client = get_client(ctx)
    resp = client.service.get("/services/licenser/pools", output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        used = int(c.get("used_bytes", 0))
        quota = int(c.get("effective_quota", 0))
        rows.append(
            {
                "title": entry.get("name", ""),
                "used": _human_bytes(used),
                "quota": _human_bytes(quota),
            }
        )
    output.render(ctx, rows, empty="No license pools found.")


@server_group.command("kvstore")
@click.pass_context
def kvstore_status(ctx: click.Context) -> None:
    """Show KV store status."""
    client = get_client(ctx)
    resp = client.service.get("/services/kvstore/status", output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error("No KV store status available.")
        ctx.exit(1)
        return

    c: dict[str, Any] = entries[0].get("content", {})
    row: dict[str, Any] = {
        "status": c.get("current.status", ""),
        "port": c.get("current.port", ""),
        "version": c.get("current.version", ""),
        "storage_engine": c.get("current.storageEngine", ""),
        "db_path": c.get("current.dbPath", ""),
    }
    output.render(ctx, row)
