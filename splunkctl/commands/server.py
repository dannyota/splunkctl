"""Server operations — messages, license, KV store, topology health."""

import json
from datetime import UTC, datetime
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
    """Server operations — messages, license, KV store, topology health."""


@server_group.command("messages")
@guard.guarded
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
            output.error(f"Message '{dismiss}' not found.", kind="not_found")
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


# Splunk encodes "never expires" as INT32_MAX seconds.
_PERPETUAL = 2**31 - 1


def _render_license_usage(ctx: click.Context, svc: Any) -> None:
    """Render today's indexed volume vs quota plus license expiry."""
    resp = svc.get("/services/licenser/usage", output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())
    entries: list[dict[str, Any]] = body.get("entry", [])
    c: dict[str, Any] = entries[0].get("content", {}) if entries else {}
    used = int(c.get("slaves_usage_bytes", 0))
    quota = int(c.get("quota", 0))
    pct = round(used / quota * 100, 1) if quota else 0.0

    resp = svc.get("/services/licenser/licenses", output_mode="json")
    lic_body: dict[str, Any] = json.loads(resp.body.read())
    valid = 0
    expiries: list[int] = []
    for entry in lic_body.get("entry", []):
        lc: dict[str, Any] = entry.get("content", {})
        if lc.get("status") == "VALID":
            valid += 1
        exp = int(lc.get("expiration_time", _PERPETUAL))
        if exp < _PERPETUAL:
            expiries.append(exp)
    soonest = (
        datetime.fromtimestamp(min(expiries), tz=UTC).strftime("%Y-%m-%d")
        if expiries
        else "never"
    )

    output.render(
        ctx,
        {
            "used": _human_bytes(used),
            "quota": _human_bytes(quota),
            "pct_used": pct,
            "licenses_valid": valid,
            "soonest_expiry": soonest,
        },
    )


@server_group.command("license")
@click.option(
    "--usage",
    "show_usage",
    is_flag=True,
    help="Today's indexed volume vs quota and soonest license expiry.",
)
@click.pass_context
def license_pools(ctx: click.Context, *, show_usage: bool) -> None:
    """Show license pool usage, or daily volume and expiry with --usage."""
    client = get_client(ctx)
    if show_usage:
        _render_license_usage(ctx, client.service)
        return

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
    current: dict[str, Any] = c.get("current") or {}
    status_raw = current.get("status")
    status = "unknown" if not status_raw else str(status_raw).lower()
    row: dict[str, Any] = {
        "status": status,
        "port": current.get("port", ""),
        "version": current.get("version", ""),
        "storage_engine": current.get("storageEngine", ""),
        "db_path": current.get("dbPath", ""),
    }
    output.render(ctx, row)


from splunkctl.commands.server_auth import auth_group  # noqa: E402
from splunkctl.commands.server_deployment import serverclasses_group  # noqa: E402
from splunkctl.commands.server_tokens import tokens_group  # noqa: E402
from splunkctl.commands.server_topology import (  # noqa: E402
    cluster_health,
    deployment_health,
    health_report,
    search_peers,
    shcluster_health,
)
from splunkctl.commands.server_workloads import workloads_group  # noqa: E402

server_group.add_command(auth_group)
server_group.add_command(serverclasses_group)
server_group.add_command(tokens_group)
server_group.add_command(workloads_group)
server_group.add_command(cluster_health)
server_group.add_command(shcluster_health)
server_group.add_command(deployment_health)
server_group.add_command(health_report)
server_group.add_command(search_peers)
