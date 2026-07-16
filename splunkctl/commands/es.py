"""Enterprise Security — notable-event triage and correlation-search admin.

Feature-detected: every subcommand checks for the ``SplunkEnterpriseSecuritySuite``
app before acting, since ES ships as an app on top of core Splunk Enterprise
and the REST surfaces here (``notable_update``) don't exist without it.
"""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import read_results, spl_quote

_ES_APP = "SplunkEnterpriseSecuritySuite"

_STATUS_MAP: dict[str, str] = {
    "unassigned": "0",
    "new": "1",
    "in progress": "2",
    "pending": "3",
    "resolved": "4",
    "closed": "5",
}

_URGENCIES = ("informational", "low", "medium", "high", "critical")


def _require_es(ctx: click.Context) -> Any:
    """Feature-detect ES via one entity fetch; return the connected service.

    Exits 1 with a ``not_found`` envelope naming the missing app when ES
    isn't installed. Callers must check for a ``None`` return and stop.
    """
    svc = get_client(ctx).service
    try:
        svc.apps[_ES_APP]
    except KeyError:
        output.error(
            f"App '{_ES_APP}' is not installed on this instance. "
            "The 'es' command group requires Splunk Enterprise Security.",
            kind="not_found",
        )
        ctx.exit(1)
        return None
    return svc


def _status_to_int(value: str) -> str:
    """Map a canonical status name to its integer string; digits pass through.

    Raises:
        click.BadParameter: ``value`` is neither a known status name nor
            an integer string.
    """
    key = value.strip().lower()
    if key in _STATUS_MAP:
        return _STATUS_MAP[key]
    if value.isascii() and value.isdigit():
        return value
    known = ", ".join(_STATUS_MAP)
    raise click.BadParameter(f"'{value}' is not a known status ({known}, or 0-5)")


def _list_spl(
    *,
    status_filter: str | None,
    owner_filter: str | None,
    rule_filter: str | None,
) -> str:
    """Build the ``index=notable`` search with composed filters.

    Filters are folded into the SPL itself (server-side), not applied
    client-side after the fact.
    """
    clauses = ["search index=notable"]
    if status_filter is not None:
        # safe: _status_to_int guarantees an int/known-name; never raw user text
        clauses.append(f"status={_status_to_int(status_filter)}")
    if owner_filter is not None:
        clauses.append(f"owner={spl_quote(owner_filter)}")
    if rule_filter is not None:
        clauses.append(f"rule_name={spl_quote(f'*{rule_filter}*')}")
    clauses.append("| sort - _time")
    clauses.append("| rename _time as time, rule_name as rule")
    clauses.append(
        "| table time, rule, security_domain, urgency, status, owner, event_id"
    )
    return " ".join(clauses)


@click.group("es")
def es_group() -> None:
    """Enterprise Security — notable-event triage (requires ES installed)."""


@es_group.group("notables")
def notables_group() -> None:
    """List, inspect, and triage notable events."""


@notables_group.command("list")
@click.option("--since", default="-24h", help="Earliest time (default -24h).")
@click.option("--until", default="now", help="Latest time (default now).")
@click.option("--status", "status_filter", default=None, help="Status name or integer.")
@click.option("--owner", "owner_filter", default=None, help="Filter by assigned owner.")
@click.option(
    "--rule",
    "rule_filter",
    default=None,
    help="Correlation search name substring.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=100,
    help="Max results (default 100).",
)
@click.pass_context
def list_notables(
    ctx: click.Context,
    since: str,
    until: str,
    status_filter: str | None,
    owner_filter: str | None,
    rule_filter: str | None,
    limit: int,
) -> None:
    """List notable events (index=notable) with server-side filters."""
    svc = _require_es(ctx)
    if svc is None:
        return

    spl = _list_spl(
        status_filter=status_filter, owner_filter=owner_filter, rule_filter=rule_filter
    )
    output.info(f"Searching: {spl}")
    stream: Any = svc.jobs.oneshot(
        spl,
        output_mode="json",
        count=limit,
        earliest_time=since,
        latest_time=until,
    )
    rows = read_results(stream)
    output.render(ctx, rows, empty="No notable events found.")


@notables_group.command("get")
@click.argument("event_id")
@click.pass_context
def get_notable(ctx: click.Context, event_id: str) -> None:
    """Get one notable event's full field set, by event_id."""
    svc = _require_es(ctx)
    if svc is None:
        return

    spl = f"search index=notable event_id={spl_quote(event_id)} | sort - _time | head 1"
    stream: Any = svc.jobs.oneshot(spl, output_mode="json", count=1)
    rows = read_results(stream)
    if not rows:
        output.error(f"Notable '{event_id}' not found.", kind="not_found")
        ctx.exit(1)
        return
    output.render(ctx, rows[0])


@notables_group.command("update")
@guard.guarded
@click.argument("event_ids", nargs=-1, required=True)
@click.option(
    "--status",
    "status_value",
    default=None,
    help=f"New status: name ({', '.join(_STATUS_MAP)}) or integer 0-5.",
)
@click.option("--owner", "owner_value", default=None, help="New assignee (owner).")
@click.option(
    "--urgency",
    type=click.Choice(_URGENCIES),
    default=None,
    help="New urgency.",
)
@click.option(
    "--disposition",
    default=None,
    help="ES disposition id (e.g. 'disposition:1'), passed through as-is — "
    "see your ES instance's configured dispositions.",
)
@click.option("--comment", default=None, help="Analyst comment.")
@click.pass_context
def update_notables(
    ctx: click.Context,
    event_ids: tuple[str, ...],
    status_value: str | None,
    owner_value: str | None,
    urgency: str | None,
    disposition: str | None,
    comment: str | None,
) -> None:
    """Triage one or more notables: assign, set status/urgency/disposition, comment.

    Accepts multiple EVENT_IDS for bulk triage. Requires at least one of
    --status/--owner/--urgency/--disposition/--comment.
    """
    if (
        status_value is None
        and owner_value is None
        and urgency is None
        and disposition is None
        and comment is None
    ):
        raise click.BadParameter(
            "provide at least one of --status/--owner/--urgency/--disposition/--comment"
        )

    payload: dict[str, Any] = {"ruleUIDs": list(event_ids)}
    if status_value is not None:
        payload["status"] = _status_to_int(status_value)
    if owner_value is not None:
        payload["newOwner"] = owner_value
    if urgency is not None:
        payload["urgency"] = urgency
    if disposition is not None:
        payload["disposition"] = disposition
    if comment is not None:
        payload["comment"] = comment

    changes = ", ".join(f"{k}={v}" for k, v in payload.items() if k != "ruleUIDs")
    details = f"  event_ids: {', '.join(event_ids)}\n  changes: {changes}"
    if not guard.check(ctx, f"Update {len(event_ids)} notable(s)", details=details):
        return

    svc = _require_es(ctx)
    if svc is None:
        return
    svc.post("/services/notable_update", **payload)
    output.info(f"Updated {len(event_ids)} notable(s).")


# --- correlation searches ---

_CORR_SUMMARY_FIELDS = (
    "security_domain",
    "severity",
    "cron_schedule",
    "next_scheduled_time",
)


def _corr_summarize(ss: Any) -> dict[str, Any]:
    """Build a summary row for a correlation search."""
    c: dict[str, Any] = ss.content
    return {
        "name": ss.name,
        "security_domain": c.get("action.correlationsearch.label", "")
        or c.get("security_domain", ""),
        "severity": c.get("alert.severity", ""),
        "enabled": "0" if c.get("disabled", "0") == "1" else "1",
        "cron_schedule": c.get("cron_schedule", ""),
        "next_scheduled_time": c.get("next_scheduled_time", ""),
    }


def _corr_detail(ss: Any) -> dict[str, Any]:
    """Build a full detail dict for a correlation search."""
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    row: dict[str, Any] = {
        "name": ss.name,
        "app": acl.get("app", ""),
        "owner": acl.get("owner", ""),
        "sharing": acl.get("sharing", ""),
        "security_domain": c.get("action.correlationsearch.label", "")
        or c.get("security_domain", ""),
        "severity": c.get("alert.severity", ""),
        "enabled": "0" if c.get("disabled", "0") == "1" else "1",
        "disabled": c.get("disabled", "0"),
        "search": c.get("search", ""),
        "description": c.get("description", ""),
        "cron_schedule": c.get("cron_schedule", ""),
        "is_scheduled": c.get("is_scheduled", "0"),
        "next_scheduled_time": c.get("next_scheduled_time", ""),
        "actions": c.get("actions", ""),
        "dispatch.earliest_time": c.get("dispatch.earliest_time", ""),
        "dispatch.latest_time": c.get("dispatch.latest_time", ""),
    }
    return row


def _resolve_corr(
    ctx: click.Context,
    svc: Any,
    name: str,
) -> Any | None:
    """Fetch a correlation search (saved search scoped to the ES app).

    Returns ``None`` on not-found (after printing the error envelope).
    """
    matches = svc.saved_searches.list(
        search=f"name={spl_quote(name)}",
        count=10,
        app=_ES_APP,
        owner="-",
    )
    for m in matches:
        if m.name == name:
            return m
    output.error(
        f"Correlation search not found: {name}",
        kind="not_found",
    )
    ctx.exit(1)
    return None


@es_group.group("correlations")
def correlations_group() -> None:
    """Manage correlation searches (ES-scoped saved searches)."""


@correlations_group.command("list")
@click.option(
    "--enabled/--disabled",
    "enabled_filter",
    default=None,
    help="Show only enabled or disabled correlation searches.",
)
@click.option(
    "--security-domain",
    default=None,
    help="Filter by security domain (e.g. access, endpoint, network).",
)
@click.pass_context
def corr_list(
    ctx: click.Context,
    enabled_filter: bool | None,
    security_domain: str | None,
) -> None:
    """List correlation searches with ES-specific fields."""
    svc = _require_es(ctx)
    if svc is None:
        return

    items = svc.saved_searches.list(app=_ES_APP, owner="-")
    rows = [_corr_summarize(ss) for ss in items]

    if enabled_filter is not None:
        want = "1" if enabled_filter else "0"
        rows = [r for r in rows if r["enabled"] == want]
    if security_domain is not None:
        needle = security_domain.lower()
        rows = [r for r in rows if needle in r["security_domain"].lower()]

    output.render(ctx, rows, empty="No correlation searches found.")


@correlations_group.command("get")
@click.argument("name")
@click.pass_context
def corr_get(ctx: click.Context, name: str) -> None:
    """Get full detail for one correlation search."""
    svc = _require_es(ctx)
    if svc is None:
        return

    ss = _resolve_corr(ctx, svc, name)
    if ss is None:
        return
    output.render(ctx, _corr_detail(ss))


@correlations_group.command("enable")
@guard.guarded
@click.argument("names", nargs=-1, required=True)
@click.pass_context
def corr_enable(ctx: click.Context, names: tuple[str, ...]) -> None:
    """Enable one or more correlation searches."""
    detail = "  names: " + ", ".join(names)
    if not guard.check(
        ctx, f"Enable {len(names)} correlation search(es)", details=detail
    ):
        return

    svc = _require_es(ctx)
    if svc is None:
        return
    for name in names:
        ss = _resolve_corr(ctx, svc, name)
        if ss is None:
            return
        ss.update(disabled="0", is_scheduled="1").refresh()
    output.info(f"Enabled {len(names)} correlation search(es).")


@correlations_group.command("disable")
@guard.guarded
@click.argument("names", nargs=-1, required=True)
@click.pass_context
def corr_disable(ctx: click.Context, names: tuple[str, ...]) -> None:
    """Disable one or more correlation searches."""
    detail = "  names: " + ", ".join(names)
    if not guard.check(
        ctx, f"Disable {len(names)} correlation search(es)", details=detail
    ):
        return

    svc = _require_es(ctx)
    if svc is None:
        return
    for name in names:
        ss = _resolve_corr(ctx, svc, name)
        if ss is None:
            return
        ss.update(disabled="1").refresh()
    output.info(f"Disabled {len(names)} correlation search(es).")


from splunkctl.commands.es_threat_intel import threat_intel_group  # noqa: E402

es_group.add_command(threat_intel_group)
