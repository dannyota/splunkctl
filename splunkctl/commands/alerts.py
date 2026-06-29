"""Alerts commands — fired alerts, alert actions, suppression."""

from typing import Any
from urllib.parse import quote

import click

from splunkctl import output
from splunkctl.client import get_client
from splunkctl.guard import check


@click.group("alerts")
def alerts_group() -> None:
    """Manage fired alerts and alert actions."""


@alerts_group.command("list")
@click.pass_context
def list_alerts(ctx: click.Context) -> None:
    """List fired alerts."""
    client = get_client(ctx)
    rows: list[dict[str, Any]] = []
    for alert in client.service.fired_alerts:
        if alert.name == "-":
            continue
        content: dict[str, Any] = dict(alert.content)
        rows.append(
            {
                "name": alert.name,
                "count": alert.count,
                "triggered_time": content.get("triggered_time", ""),
                "severity": content.get("severity", ""),
            }
        )
    if not rows:
        output.info("No fired alerts.")
        return
    output.render(ctx, rows)


@alerts_group.command("get")
@click.argument("name")
@click.pass_context
def get_alert(ctx: click.Context, name: str) -> None:
    """Get details of a specific fired alert group."""
    client = get_client(ctx)
    try:
        alert = client.service.fired_alerts[name]
    except KeyError:
        output.error(f"Fired alert not found: {name}")
        ctx.exit(1)
        return
    row: dict[str, Any] = {"name": alert.name, "count": alert.count}
    row.update(dict(alert.content))
    output.render(ctx, row)


@alerts_group.command("actions")
@click.pass_context
def list_actions(ctx: click.Context) -> None:
    """List available alert action types."""
    client = get_client(ctx)
    rows: list[dict[str, Any]] = []
    for stanza in client.service.confs["alert_actions"]:
        content: dict[str, Any] = dict(stanza.content)
        rows.append(
            {
                "name": stanza.name,
                "label": content.get("label", ""),
                "description": content.get("description", ""),
            }
        )
    output.render(ctx, rows)


@alerts_group.command("suppress")
@click.argument("name")
@click.option(
    "--duration",
    type=int,
    default=3600,
    help="Suppression duration in seconds.",
)
@click.pass_context
def suppress_alert(ctx: click.Context, name: str, duration: int) -> None:
    """Suppress a fired alert (guarded)."""
    details = f"Suppress '{name}' for {duration}s"
    if not check(ctx, "suppress fired alert", details=details):
        return
    client = get_client(ctx)
    path = f"/services/alerts/fired_alerts/{quote(name, safe='')}"
    client.service.post(path, suppress="1", expiration=str(duration))
    output.info(f"Suppressed: {name} for {duration}s")
