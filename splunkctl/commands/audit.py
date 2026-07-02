"""``audit`` group — change audit and RBAC attestation, for regulator evidence.

Both subcommands are read-only (no ``guard``).

``changes`` wraps ``index=_audit`` without ever composing user input into
SPL: the dispatched search is always the constant ``search index=_audit``.
Time bounds go through the oneshot job's ``earliest_time``/``latest_time``
kwargs, and ``--user``/``--action``/``--object-type`` filter the
already-normalized rows client-side, after the fetch.

``rbac`` joins users/roles/capabilities/index-restrictions via SDK reads
only, for periodic access recertification evidence.
"""

from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client
from splunkctl.commands.audit_parse import parse_event
from splunkctl.commands.common import read_results

_AUDIT_SPL = "search index=_audit"


def _as_list(value: Any) -> list[str]:
    """Normalize a Splunk multi-value field that may come back as a bare string.

    The REST API returns a plain string instead of a one-item list when a
    multi-value field has exactly one value.
    """
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _transitive_roles(
    direct: list[str], role_map: dict[str, dict[str, Any]]
) -> list[str]:
    """Full ``imported_roles`` closure of ``direct`` (self included, cycle-safe)."""
    seen: set[str] = set()
    stack = list(direct)
    while stack:
        name = stack.pop()
        if name in seen or name not in role_map:
            continue
        seen.add(name)
        stack.extend(_as_list(role_map[name].get("imported_roles", [])))
    return sorted(seen)


def _aggregate(
    names: list[str], role_map: dict[str, dict[str, Any]], field: str
) -> str:
    r"""Union ``field`` across ``names``, deduplicated, sorted, semicolon-joined.

    ``;`` (never ``\n``) so aggregated multi-value cells stay one CSV field.
    """
    values: set[str] = set()
    for name in names:
        content = role_map.get(name)
        if content is not None:
            values.update(_as_list(content.get(field, [])))
    return ";".join(sorted(values))


def _user_row(user: Any, role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    content: dict[str, Any] = user.content
    direct = _as_list(content.get("roles", []))
    effective = _transitive_roles(direct, role_map)
    return {
        "user": user.name,
        "email": str(content.get("email") or ""),
        "roles": ";".join(sorted(direct)),
        "capabilities": _aggregate(effective, role_map, "capabilities"),
        "srch_indexes_allowed": _aggregate(effective, role_map, "srchIndexesAllowed"),
    }


def _role_row(name: str, role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    imported = _as_list(role_map[name].get("imported_roles", []))
    effective = _transitive_roles([name], role_map)
    return {
        "role": name,
        "imported_roles": ";".join(sorted(imported)),
        "capabilities": _aggregate(effective, role_map, "capabilities"),
        "srch_indexes_allowed": _aggregate(effective, role_map, "srchIndexesAllowed"),
    }


@click.group("audit")
def audit_group() -> None:
    """Change audit and RBAC attestation — regulator evidence, read-only."""


@audit_group.command("changes")
@click.option("--since", default="-24h", help="Earliest time (default -24h).")
@click.option("--until", default="now", help="Latest time (default now).")
@click.option(
    "--user", "user_filter", default=None, help="Filter by user (exact match)."
)
@click.option(
    "--action",
    "action_filter",
    default=None,
    help="Filter by action (substring match).",
)
@click.option(
    "--object-type",
    "object_type_filter",
    default=None,
    help="Filter by object type (exact match).",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=500,
    help="Max results after client-side filtering (default 500).",
)
@click.pass_context
def changes(
    ctx: click.Context,
    since: str,
    until: str,
    user_filter: str | None,
    action_filter: str | None,
    object_type_filter: str | None,
    limit: int,
) -> None:
    """Normalized index=_audit change events (both legacy and JSON shapes).

    SECURITY: the dispatched SPL is always the constant
    ``search index=_audit``. --since/--until go through the search job's
    time-range kwargs; --user/--action/--object-type filter the
    normalized rows client-side. No flag value is ever composed into the
    SPL string.
    """
    client = get_client(ctx)
    svc = client.service

    output.info(f"Searching: {_AUDIT_SPL}")
    stream: Any = svc.jobs.oneshot(
        _AUDIT_SPL,
        output_mode="json",
        count=0,
        earliest_time=since,
        latest_time=until,
    )
    rows = [parse_event(r) for r in read_results(stream)]

    if user_filter is not None:
        rows = [r for r in rows if r["user"] == user_filter]
    if action_filter is not None:
        needle = action_filter.lower()
        rows = [r for r in rows if needle in r["action"].lower()]
    if object_type_filter is not None:
        rows = [r for r in rows if r["object_type"] == object_type_filter]

    rows.sort(key=lambda r: r["time"], reverse=True)
    output.render(ctx, rows[:limit], empty="No audit events found.")


@audit_group.command("rbac")
@click.option(
    "--roles-only",
    is_flag=True,
    help="One row per role instead of per user (role-centric attestation view).",
)
@click.pass_context
def rbac(ctx: click.Context, *, roles_only: bool) -> None:
    """Users x roles x capabilities x index-restrictions — recertification evidence.

    Capabilities and srch_indexes_allowed are aggregated across each
    principal's direct roles AND the full transitive closure of their
    imported roles, deduplicated and sorted.
    """
    client = get_client(ctx)
    svc = client.service

    role_map: dict[str, dict[str, Any]] = {r.name: dict(r.content) for r in svc.roles}

    if roles_only:
        rows = [_role_row(name, role_map) for name in sorted(role_map)]
        output.render(ctx, rows, empty="No roles found.")
        return

    users = sorted(svc.users, key=lambda u: str(u.name))
    user_rows = [_user_row(u, role_map) for u in users]
    output.render(ctx, user_rows, empty="No users found.")
