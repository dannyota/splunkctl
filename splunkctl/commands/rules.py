"""Saved searches / detection rules."""

import time
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import common
from splunkctl.commands.common import read_results, spl_quote
from splunkctl.commands.rules_io import export_rules, import_rules


def _resolve_rule(
    ctx: click.Context,
    client: Any,
    name: str,
    app: str | None,
    owner: str | None = None,
) -> Any:
    """Fetch a saved search, optionally scoped to an app/owner namespace."""
    svc = client.service
    if app is None and owner is None:
        try:
            return svc.saved_searches[name]
        except KeyError:
            output.error(f"Saved search not found: {name}", kind="not_found")
            ctx.exit(1)
            raise
    scope_kwargs: dict[str, str] = {}
    if app is not None:
        scope_kwargs["app"] = app
        scope_kwargs["owner"] = owner if owner is not None else "-"
    elif owner is not None:
        scope_kwargs["owner"] = owner
    matches = svc.saved_searches.list(
        search=f"name={spl_quote(name)}", count=10, **scope_kwargs
    )
    for m in matches:
        if m.name == name:
            return m
    scope = ", ".join(f"{k}={v}" for k, v in scope_kwargs.items())
    output.error(f"Saved search not found ({scope}): {name}", kind="not_found")
    ctx.exit(1)
    raise KeyError(name)


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
        "severity": c.get("alert.severity", ""),
        "description": c.get("description", ""),
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
    "alert_comparator",
    "alert_threshold",
    "alert.severity",
    "alert.suppress",
    "alert.suppress.period",
    "alert.track",
    "dispatch.earliest_time",
    "dispatch.latest_time",
    "schedule_window",
    "max_concurrent",
    "realtime_schedule",
    "request.ui_dispatch_app",
)


def _action_params(c: dict[str, Any]) -> dict[str, Any]:
    """Non-empty ``action.<name>.*`` content keys for each enabled action."""
    actions = str(c.get("actions", "") or "")
    params: dict[str, Any] = {}
    for act in (a.strip() for a in actions.split(",") if a.strip()):
        prefix = f"action.{act}."
        for key, val in c.items():
            if key.startswith(prefix) and val not in ("", None):
                params[key] = val
    return params


def _detail(ss: Any) -> dict[str, Any]:
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    row: dict[str, Any] = {
        "name": ss.name,
        "app": acl.get("app", ""),
        "owner": acl.get("owner", ""),
        "sharing": acl.get("sharing", ""),
    }
    row.update({f: c.get(f, "") for f in _DETAIL_FIELDS})
    row.update(_action_params(c))
    return row


@click.group("rules")
def rules_group() -> None:
    """Manage detection rules (saved searches)."""


rules_group.add_command(export_rules)
rules_group.add_command(import_rules)


@rules_group.command("list")
@click.option(
    "--app",
    default=None,
    help="Only saved searches in this app (default: current namespace, which "
    "may miss app-private rules — pass --app to see them).",
)
@click.option(
    "--owner",
    default=None,
    help="Only saved searches owned by this user (default: current namespace).",
)
@common.list_options
@click.pass_context
def list_rules(
    ctx: click.Context,
    *,
    app: str | None,
    owner: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List all saved searches."""
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
    rows = [_summarize(ss) for ss in items]
    output.render(ctx, rows, empty="No saved searches found.")


@rules_group.command()
@click.argument("name")
@click.option(
    "--app",
    default=None,
    help="Splunk app context (needed to resolve app-private saved searches).",
)
@click.option("--owner", default=None, help="Splunk owner context.")
@click.pass_context
def get(ctx: click.Context, name: str, *, app: str | None, owner: str | None) -> None:
    """Get a saved search by name."""
    client = get_client(ctx)
    ss = _resolve_rule(ctx, client, name, app, owner)
    output.render(ctx, _detail(ss))


@rules_group.command()
@guard.guarded
@click.option("--name", required=True, help="Saved search name.")
@click.option("--search", "spl", required=True, help="SPL query.")
@click.option("--cron", default=None, help="Cron schedule.")
@click.option("--app", default=None, help="Splunk app context.")
@click.option("--description", default=None, help="Description.")
@click.option("--actions", default=None, help="Alert actions (comma-separated).")
@click.option("--disabled", is_flag=True, default=False, help="Create disabled.")
@common.alert_options
@click.pass_context
def create(
    ctx: click.Context,
    /,
    *,
    name: str,
    spl: str,
    cron: str | None,
    app: str | None,
    description: str | None,
    actions: str | None,
    disabled: bool,
    **alert_flags: Any,
) -> None:
    """Create a saved search."""
    kwargs: dict[str, Any] = dict(common.alert_kwargs(actions=actions, **alert_flags))
    if cron is not None:
        kwargs["cron_schedule"] = cron
        kwargs["is_scheduled"] = "1"
    if description is not None:
        kwargs["description"] = description
    if actions is not None:
        kwargs["actions"] = actions
        common.warn_missing_action_fields(actions, kwargs)
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
@guard.guarded
@click.argument("name")
@click.option("--search", "spl", default=None, help="SPL query.")
@click.option("--cron", default=None, help="Cron schedule.")
@click.option("--app", default=None, help="Splunk app context of the rule.")
@click.option("--description", default=None, help="Description.")
@click.option("--actions", default=None, help="Alert actions (comma-separated).")
@click.option(
    "--enabled/--disabled",
    default=None,
    help="Enable or disable scheduling.",
)
@common.alert_options
@click.pass_context
def update(
    ctx: click.Context,
    /,
    name: str,
    *,
    spl: str | None,
    cron: str | None,
    app: str | None,
    description: str | None,
    actions: str | None,
    enabled: bool | None,
    **alert_flags: Any,
) -> None:
    """Update a saved search."""
    kwargs: dict[str, Any] = dict(common.alert_kwargs(actions=actions, **alert_flags))
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

    # Only fetch the existing rule up front when a required-field check
    # against server-side state is needed — keeps other dry-runs offline.
    client: Any = None
    ss: Any = None
    if actions is not None:
        client = get_client(ctx)
        ss = _resolve_rule(ctx, client, name, app)
        common.warn_missing_action_fields(actions, kwargs, ss.content)

    detail = "\n".join(f"  {k}: {v}" for k, v in kwargs.items())
    if not guard.check(ctx, f"Update saved search '{name}'", details=detail):
        return

    if ss is None:
        client = get_client(ctx)
        ss = _resolve_rule(ctx, client, name, app)
    ss.update(**kwargs).refresh()
    output.info(f"Updated saved search '{name}'.")


@rules_group.command()
@guard.guarded
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
        output.error(f"Saved search not found: {name}", kind="not_found")
        ctx.exit(1)
        return
    ss.delete()
    output.info(f"Deleted saved search '{name}'.")


@rules_group.command()
@guard.guarded
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
        output.error(f"Saved search not found: {name}", kind="not_found")
        ctx.exit(1)
        return
    ss.update(disabled="0", is_scheduled="1").refresh()
    output.info(f"Enabled saved search '{name}'.")


@rules_group.command()
@guard.guarded
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
        output.error(f"Saved search not found: {name}", kind="not_found")
        ctx.exit(1)
        return
    ss.update(disabled="1").refresh()
    output.info(f"Disabled saved search '{name}'.")


@rules_group.command()
@guard.guarded
@click.argument("name")
@click.option(
    "--sharing",
    required=True,
    type=click.Choice(["user", "app", "global"]),
    help="Target sharing level.",
)
@click.option("--owner", default=None, help="New owner (defaults to current).")
@click.pass_context
def share(ctx: click.Context, name: str, sharing: str, owner: str | None) -> None:
    """Change a saved search's sharing level (ACL)."""
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}", kind="not_found")
        ctx.exit(1)
        return
    current = dict(ss.access).get("sharing", "?")
    details = f"  sharing: {current} -> {sharing}"
    if owner:
        details += f"\n  owner: {owner}"
    if not guard.check(ctx, f"Share saved search '{name}'", details=details):
        return
    client.set_acl(ss, sharing=sharing, owner=owner)
    output.info(f"Saved search '{name}' is now {sharing}-shared.")


@rules_group.command("test")
@click.argument("name")
@click.option("--earliest", default=None, help="Override dispatch window start.")
@click.option("--latest", default=None, help="Override dispatch window end.")
@click.option("--limit", default=100, type=int, help="Max results (default 100).")
@click.pass_context
def test_rule(
    ctx: click.Context,
    name: str,
    earliest: str | None,
    latest: str | None,
    limit: int,
) -> None:
    """Dispatch a rule now (backfill/test run) without firing alert actions."""
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}", kind="not_found")
        ctx.exit(1)
        return

    kwargs: dict[str, str] = {"trigger_actions": "0"}
    if earliest:
        kwargs["dispatch.earliest_time"] = earliest
    if latest:
        kwargs["dispatch.latest_time"] = latest

    output.info(f"Dispatching '{name}'" + (f" over {earliest or '(rule window)'}"))
    job: Any = ss.dispatch(**kwargs)

    timeout: int = ctx.obj.get("timeout", 30)
    deadline = time.monotonic() + timeout
    while not job.is_done():
        if time.monotonic() > deadline:
            job.cancel()
            output.error(f"Test run timed out after {timeout}s.", kind="timeout")
            ctx.exit(1)
            return
        time.sleep(0.5)
        job.refresh()

    rows = read_results(job.results(output_mode="json", count=limit))
    output.info(f"{len(rows)} result(s); alert actions were not triggered.")
    output.render(ctx, rows, empty="No results — the rule would not have fired.")


@rules_group.command()
@click.argument("name")
@click.pass_context
def history(ctx: click.Context, name: str) -> None:
    """Show run history for a saved search."""
    client = get_client(ctx)
    try:
        ss = client.service.saved_searches[name]
    except KeyError:
        output.error(f"Saved search not found: {name}", kind="not_found")
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
