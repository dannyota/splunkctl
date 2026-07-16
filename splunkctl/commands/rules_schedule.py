"""Scheduler health view for saved searches."""

from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client
from splunkctl.commands import common


def _schedule_row(ss: Any) -> dict[str, Any]:
    """Build a schedule-health row from a saved search entity."""
    c: dict[str, Any] = ss.content
    earliest = c.get("dispatch.earliest_time", "")
    latest = c.get("dispatch.latest_time", "")
    window = f"{earliest} to {latest}" if earliest or latest else ""
    disabled = str(c.get("disabled", "0"))
    return {
        "name": ss.name,
        "cron": c.get("cron_schedule", ""),
        "next_run": c.get("next_scheduled_time", ""),
        "window": window,
        "enabled": "no" if disabled == "1" else "yes",
    }


def _schedule_detail(ss: Any) -> dict[str, Any]:
    """Full schedule detail for JSON output."""
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    search = str(c.get("search", ""))
    return {
        "name": ss.name,
        "app": acl.get("app", ""),
        "cron_schedule": c.get("cron_schedule", ""),
        "next_scheduled_time": c.get("next_scheduled_time", ""),
        "dispatch.earliest_time": c.get("dispatch.earliest_time", ""),
        "dispatch.latest_time": c.get("dispatch.latest_time", ""),
        "is_scheduled": c.get("is_scheduled", "0"),
        "disabled": c.get("disabled", "0"),
        "qualifiedSearch": search,
    }


@click.command("schedule")
@click.option(
    "--app",
    default=None,
    help="Only saved searches in this app.",
)
@click.option(
    "--owner",
    default=None,
    help="Only saved searches owned by this user.",
)
@common.list_options
@click.pass_context
def schedule_cmd(
    ctx: click.Context,
    *,
    app: str | None,
    owner: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """Show scheduling info for saved searches (scheduler health)."""
    client = get_client(ctx)
    kwargs: dict[str, str] = {}
    if app is not None:
        kwargs["app"] = app
        kwargs["owner"] = owner if owner is not None else "-"
    elif owner is not None:
        kwargs["owner"] = owner
    items = common.fetch_page(
        lambda **pg: client.service.saved_searches.list(**kwargs, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    # Filter to scheduled searches only.
    items = [ss for ss in items if str(ss.content.get("is_scheduled", "0")) == "1"]

    obj: dict[str, Any] = ctx.obj or {}
    use_json: bool = obj.get("json", False) or obj.get("format") in (
        "json",
        "jsonl",
        "csv",
    )

    if use_json:
        rows = [_schedule_detail(ss) for ss in items]
    else:
        rows = [_schedule_row(ss) for ss in items]

    output.render(ctx, rows, empty="No scheduled saved searches found.")
