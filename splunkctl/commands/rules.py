"""Saved searches / detection rules."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


def _summarize(ss: Any) -> dict[str, Any]:
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    return {
        "name": ss.name,
        "app": acl.get("app", ""),
        "is_scheduled": c.get("is_scheduled", "0"),
        "cron": c.get("cron_schedule", ""),
        "next_scheduled": c.get("next_scheduled_time", ""),
        "disabled": c.get("disabled", "0"),
        "actions": c.get("actions", ""),
    }


_DETAIL_FIELDS = (
    "search",
    "description",
    "cron_schedule",
    "is_scheduled",
    "next_scheduled_time",
    "disabled",
    "actions",
    "alert_type",
    "alert.severity",
    "alert.suppress",
    "dispatch.earliest_time",
    "dispatch.latest_time",
    "max_concurrent",
    "realtime_schedule",
    "request.ui_dispatch_app",
)


def _detail(ss: Any) -> dict[str, Any]:
    c: dict[str, Any] = ss.content
    row: dict[str, Any] = {"name": ss.name}
    row.update({f: c.get(f, "") for f in _DETAIL_FIELDS})
    return row


@click.group("rules")
def rules_group() -> None:
    """Manage detection rules (saved searches)."""


@rules_group.command("list")
@click.pass_context
def list_rules(ctx: click.Context) -> None:
    """List all saved searches."""
    client = get_client(ctx)
    items = client.service.saved_searches.list()
    rows = [_summarize(ss) for ss in items]
    output.render(ctx, rows)


@rules_group.command()
@click.argument("name")
@click.pass_context
def get(ctx: click.Context, name: str) -> None:
    """Get a saved search by name."""
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    output.render(ctx, _detail(ss))


@rules_group.command()
@click.option("--name", required=True, help="Saved search name.")
@click.option("--search", "spl", required=True, help="SPL query.")
@click.option("--cron", default=None, help="Cron schedule.")
@click.option("--app", default=None, help="Splunk app context.")
@click.option("--description", default=None, help="Description.")
@click.option("--actions", default=None, help="Alert actions (comma-separated).")
@click.option("--disabled", is_flag=True, default=False, help="Create disabled.")
@click.pass_context
def create(
    ctx: click.Context,
    *,
    name: str,
    spl: str,
    cron: str | None,
    app: str | None,
    description: str | None,
    actions: str | None,
    disabled: bool,
) -> None:
    """Create a saved search."""
    kwargs: dict[str, Any] = {}
    if cron is not None:
        kwargs["cron_schedule"] = cron
        kwargs["is_scheduled"] = "1"
    if description is not None:
        kwargs["description"] = description
    if actions is not None:
        kwargs["actions"] = actions
    if disabled:
        kwargs["disabled"] = "1"
    if app is not None:
        kwargs["app"] = app

    detail = f"  name:   {name}\n  search: {spl}"
    if kwargs:
        detail += "\n  " + "\n  ".join(f"{k}: {v}" for k, v in kwargs.items())

    if not guard.check(ctx, f"Create saved search '{name}'", details=detail):
        return

    client = get_client(ctx)
    client.service.saved_searches.create(name, search=spl, **kwargs)
    output.info(f"Created saved search '{name}'.")


@rules_group.command()
@click.argument("name")
@click.option("--search", "spl", default=None, help="SPL query.")
@click.option("--cron", default=None, help="Cron schedule.")
@click.option("--description", default=None, help="Description.")
@click.option("--actions", default=None, help="Alert actions (comma-separated).")
@click.option(
    "--enabled/--disabled",
    default=None,
    help="Enable or disable scheduling.",
)
@click.pass_context
def update(
    ctx: click.Context,
    name: str,
    *,
    spl: str | None,
    cron: str | None,
    description: str | None,
    actions: str | None,
    enabled: bool | None,
) -> None:
    """Update a saved search."""
    kwargs: dict[str, Any] = {}
    if spl is not None:
        kwargs["search"] = spl
    if cron is not None:
        kwargs["cron_schedule"] = cron
    if description is not None:
        kwargs["description"] = description
    if actions is not None:
        kwargs["actions"] = actions
    if enabled is not None:
        kwargs["disabled"] = "0" if enabled else "1"
        if enabled:
            kwargs["is_scheduled"] = "1"

    if not kwargs:
        output.error("No changes specified.")
        ctx.exit(1)
        return

    detail = "\n".join(f"  {k}: {v}" for k, v in kwargs.items())
    if not guard.check(ctx, f"Update saved search '{name}'", details=detail):
        return

    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.update(**kwargs).refresh()
    output.info(f"Updated saved search '{name}'.")


@rules_group.command()
@click.argument("name")
@click.pass_context
def delete(ctx: click.Context, name: str) -> None:
    """Delete a saved search."""
    if not guard.check(ctx, f"Delete saved search '{name}'"):
        return

    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.delete()
    output.info(f"Deleted saved search '{name}'.")


@rules_group.command()
@click.argument("name")
@click.pass_context
def enable(ctx: click.Context, name: str) -> None:
    """Enable scheduling for a saved search."""
    if not guard.check(ctx, f"Enable saved search '{name}'"):
        return

    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.update(disabled="0", is_scheduled="1").refresh()
    output.info(f"Enabled saved search '{name}'.")


@rules_group.command()
@click.argument("name")
@click.pass_context
def disable(ctx: click.Context, name: str) -> None:
    """Disable scheduling for a saved search."""
    if not guard.check(ctx, f"Disable saved search '{name}'"):
        return

    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    ss.update(disabled="1").refresh()
    output.info(f"Disabled saved search '{name}'.")


@rules_group.command()
@click.argument("name")
@click.pass_context
def history(ctx: click.Context, name: str) -> None:
    """Show run history for a saved search."""
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}")
        ctx.exit(1)
        return
    jobs = ss.history()
    rows: list[dict[str, Any]] = []
    for job in jobs:
        c: dict[str, Any] = job.content
        rows.append(
            {
                "sid": job.sid,
                "dispatch_state": c.get("dispatchState", ""),
                "run_duration": c.get("runDuration", ""),
                "event_count": c.get("eventCount", ""),
                "result_count": c.get("resultCount", ""),
            }
        )
    output.render(ctx, rows)
