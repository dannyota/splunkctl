"""SOAR admin — roles & audit log."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError


def _cap_csv(text: str, limit: int) -> str:
    """Truncate CSV *text* to header + *limit* rows (quote-aware)."""
    reader = csv.reader(io.StringIO(text))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for i, row in enumerate(reader):
        if i > limit:
            break
        writer.writerow(row)
    return buf.getvalue()


# ── roles ────────────────────────────────────────────────────────────


@click.group("roles")
def roles_group() -> None:
    """SOAR role management (7 immutable built-in roles)."""


@roles_group.command("list")
@click.pass_context
def roles_list(ctx: click.Context) -> None:
    """List all SOAR roles with permissions."""
    client = get_soar_client(ctx)
    try:
        result = client.get("role", params={"page_size": 200})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    rows = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, rows, empty="No roles found.")


@roles_group.command("get")
@click.argument("role_id", type=int)
@click.pass_context
def roles_get(ctx: click.Context, *, role_id: int) -> None:
    """Get a SOAR role by ID (includes permission matrix)."""
    client = get_soar_client(ctx)
    try:
        result = client.get(f"role/{role_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"Role {role_id} not found.")


# ── audit ────────────────────────────────────────────────────────────


@click.command("audit")
@click.option("--user", "user_filter", default=None, help="Filter by username.")
@click.option(
    "--playbook",
    "playbook_filter",
    default=None,
    help="Filter by playbook name.",
)
@click.option(
    "--container",
    "container_filter",
    default=None,
    type=int,
    help="Filter by container ID.",
)
@click.option("--start", default=None, help="Start time (ISO 8601).")
@click.option("--end", default=None, help="End time (ISO 8601).")
@click.option(
    "--format",
    "out_format",
    default=None,
    type=click.Choice(["csv"]),
    help="Request CSV from server.",
)
@click.option(
    "--limit",
    default=None,
    type=click.IntRange(min=1),
    help="Max rows.",
)
@click.pass_context
def audit_cmd(
    ctx: click.Context,
    *,
    user_filter: str | None,
    playbook_filter: str | None,
    container_filter: int | None,
    start: str | None,
    end: str | None,
    out_format: str | None,
    limit: int | None,
) -> None:
    """Query the SOAR audit log (bare-array endpoint, normalized)."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {}
    if user_filter is not None:
        params["_filter_username__icontains"] = json.dumps(user_filter)
    if playbook_filter is not None:
        params["_filter_playbook__icontains"] = json.dumps(playbook_filter)
    if container_filter is not None:
        params["_filter_container"] = str(container_filter)
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    if limit is not None:
        params["page_size"] = limit

    # CSV: the server returns raw CSV text (Content-Type: application/csv),
    # not JSON. Fetch as bytes and print directly.
    if out_format == "csv":
        params["format"] = "csv"
        try:
            raw = client.get_bytes("audit", params=params)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        text = raw.decode("utf-8")
        if limit is not None:
            # The bare-array audit endpoint ignores page_size — enforce
            # the row cap client-side here too, not just for JSON.
            text = _cap_csv(text, limit)
        click.echo(text, nl=False)
        return

    try:
        result = client.get("audit", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    rows = result.get("data", []) if isinstance(result, dict) else []
    if limit is not None:
        # The bare-array audit endpoint ignores page_size — enforce
        # the row cap client-side.
        rows = rows[:limit]
    output.render(ctx, rows, empty="No audit entries found.")
