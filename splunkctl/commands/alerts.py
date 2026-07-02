"""Alerts commands — fired alerts, alert actions, suppression."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import filter_by_name, list_options, page_slice


def _firing_rows(group: Any) -> list[dict[str, Any]]:
    """One row per triggered alert in a fired-alert group."""
    rows: list[dict[str, Any]] = []
    for firing in group.alerts:
        c: dict[str, Any] = dict(firing.content)
        rows.append(
            {
                "rule": group.name,
                "triggered": c.get("trigger_time_rendered", c.get("trigger_time", "")),
                "severity": c.get("severity", ""),
                "sid": c.get("sid", ""),
                "actions": c.get("actions", ""),
            }
        )
    return rows


@click.group("alerts")
def alerts_group() -> None:
    """Manage fired alerts and alert actions."""


@alerts_group.command("list")
@list_options
@click.pass_context
def list_alerts(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List fired alerts (one row per firing, with sid for drill-down).

    --filter matches the rule name; --limit/--offset page the firing rows
    client-side (a row is one firing, not one rule).
    """
    client = get_client(ctx)
    rows: list[dict[str, Any]] = []
    for group in client.service.fired_alerts:
        if group.name == "-":
            continue
        rows.extend(_firing_rows(group))
    rows = filter_by_name(rows, name_filter, name_of=lambda r: str(r["rule"]))
    rows = page_slice(rows, limit=limit, offset=offset)
    output.render(ctx, rows, empty="No fired alerts.")


@alerts_group.command("get")
@click.argument("name")
@click.pass_context
def get_alert(ctx: click.Context, name: str) -> None:
    """Get every firing of a fired-alert group."""
    client = get_client(ctx)
    for group in client.service.fired_alerts:
        if group.name == name:
            rows = _firing_rows(group)
            output.info(f"{name}: {len(rows)} firing(s)")
            output.render(ctx, rows)
            return
    output.error(f"Fired alert not found: {name}")
    ctx.exit(1)


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
@guard.guarded
@click.argument("name")
@click.option(
    "--duration",
    type=int,
    default=3600,
    help="Throttle window in seconds.",
)
@click.pass_context
def suppress_alert(ctx: click.Context, name: str, duration: int) -> None:
    """Throttle a rule's alerts by setting alert.suppress on its saved search.

    Splunk's fired-alerts endpoint cannot be edited; throttling is a
    property of the underlying saved search.
    """
    details = (
        f"Set alert.suppress=1, alert.suppress.period={duration}s "
        f"on saved search '{name}'"
    )
    if not guard.check(ctx, "Throttle alerts for rule", details=details):
        return
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.update(
        **{"alert.suppress": "1", "alert.suppress.period": f"{duration}s"}
    ).refresh()
    output.info(f"Throttled '{name}' for {duration}s.")


@alerts_group.command("unsuppress")
@guard.guarded
@click.argument("name")
@click.pass_context
def unsuppress_alert(ctx: click.Context, name: str) -> None:
    """Remove alert throttling from a rule's saved search."""
    if not guard.check(ctx, f"Remove alert throttling from '{name}'"):
        return
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.update(**{"alert.suppress": "0"}).refresh()
    output.info(f"Removed throttling from '{name}'.")
