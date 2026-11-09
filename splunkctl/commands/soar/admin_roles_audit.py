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
    page_size = min(limit or 100, 100)
    params["page_size"] = page_size
    rows: list[Any] = []
    previous: list[Any] | None = None
    header: list[str] | None = None
    page = 1
    if out_format == "csv":
        params["format"] = "csv"
    try:
        while True:
            # Audit uses 1-based pages; num_pages is synthetic for bare arrays.
            page_params = {**params, "page": page}
            if out_format == "csv":
                raw = client.get_bytes("audit", params=page_params)
                parsed = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
                if header is None and parsed:
                    header = parsed[0]
                batch = parsed[1:]
            else:
                result = client.get("audit", params=page_params)
                batch = result.get("data", []) if isinstance(result, dict) else []
            # Older servers may ignore page or page_size. Avoid duplicate pages.
            if not batch or batch == previous:
                break
            rows.extend(batch)
            if (limit is not None and len(rows) >= limit) or len(batch) != page_size:
                break
            previous = batch
            page += 1
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    if limit is not None:
        rows = rows[:limit]
    if out_format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
        click.echo(buf.getvalue(), nl=False)
        return
    output.render(ctx, rows, empty="No audit entries found.")
