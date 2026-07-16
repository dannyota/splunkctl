"""SOAR workbook templates — list, get, create, update, delete."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError

_EP = "workbook_template"


def _resolve_template_id(
    ctx: click.Context,
    client: Any,
    ref: str,
) -> int | None:
    """Resolve a name-or-id reference to a workbook_template id.

    Returns the integer id, or None after printing an error.
    """
    if ref.isascii() and ref.isdigit():
        return int(ref)

    # Name lookup.
    try:
        result = client.get(_EP, params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return None

    data = result.get("data", []) if isinstance(result, dict) else []
    for t in data:
        if t.get("name") == ref:
            return int(t["id"])

    names = ", ".join(t.get("name", "?") for t in data) if data else "(none)"
    output.error(
        f"Workbook template '{ref}' not found. Available: {names}",
        kind="not_found",
    )
    ctx.exit(1)
    return None


@click.group("workbook-templates")
def workbook_templates_group() -> None:
    """Workbook template CRUD — list, get, create, update, delete."""


@workbook_templates_group.command("list")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Page size.")
@click.pass_context
def list_cmd(ctx: click.Context, *, limit: int | None) -> None:
    """List all workbook templates."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {}
    if limit is not None:
        params["page_size"] = limit

    try:
        result = client.get(_EP, params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No workbook templates found.")


@workbook_templates_group.command("get")
@click.argument("ref")
@click.pass_context
def get_cmd(ctx: click.Context, *, ref: str) -> None:
    """Get a workbook template by name or id."""
    client = get_soar_client(ctx)
    template_id = _resolve_template_id(ctx, client, ref)
    if template_id is None:
        return

    try:
        result = client.get(f"{_EP}/{template_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, {}, empty="No data.")


@workbook_templates_group.command("create")
@guard.guarded
@click.option("--name", required=True, help="Template name.")
@click.option(
    "--phases",
    required=True,
    help="Comma-separated phase names (e.g. 'Detect,Contain,Recover').",
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    *,
    name: str,
    phases: str,
) -> None:
    """Create a workbook template with named phases."""
    phase_list = [p.strip() for p in phases.split(",") if p.strip()]
    if not phase_list:
        output.error("At least one phase name is required.", kind="usage")
        ctx.exit(1)
        return

    phase_dicts = [{"name": p, "order": i} for i, p in enumerate(phase_list, start=1)]
    body: dict[str, Any] = {"name": name, "phases": phase_dicts}

    details = f"  name: {name}\n  phases: {', '.join(phase_list)}"
    if not guard.soar_check(
        ctx,
        f"Create workbook template '{name}'",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post(_EP, body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Workbook template created: id={new_id}")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


@workbook_templates_group.command("update")
@guard.guarded
@click.argument("ref")
@click.option(
    "--add-phase",
    "add_phases",
    multiple=True,
    help="Phase name to add (repeatable).",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    *,
    ref: str,
    add_phases: tuple[str, ...],
) -> None:
    """Update a workbook template — add phases."""
    if not add_phases:
        output.error("No updates specified. Use --add-phase.", kind="usage")
        ctx.exit(1)
        return

    details = f"  template: {ref}\n  add phases: {', '.join(add_phases)}"
    if not guard.soar_check(
        ctx,
        f"Update workbook template {ref}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    template_id = _resolve_template_id(ctx, client, ref)
    if template_id is None:
        return

    # Fetch existing template to get current phases for ordering.
    try:
        current = client.get(f"{_EP}/{template_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    existing_phases: list[dict[str, Any]] = []
    if isinstance(current, dict):
        existing_phases = current.get("phases", [])

    max_order = max((p.get("order", 0) for p in existing_phases), default=0)

    new_phases = [
        {"name": name, "order": max_order + i}
        for i, name in enumerate(add_phases, start=1)
    ]
    body: dict[str, Any] = {"phases": existing_phases + new_phases}

    try:
        client.post(f"{_EP}/{template_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Template {template_id} updated: added {len(add_phases)} phase(s).")


@workbook_templates_group.command("delete")
@guard.guarded
@click.argument("ref")
@click.pass_context
def delete_cmd(ctx: click.Context, *, ref: str) -> None:
    """Delete a workbook template by name or id."""
    if not guard.soar_check(ctx, f"Delete workbook template {ref}"):
        return

    client = get_soar_client(ctx)
    template_id = _resolve_template_id(ctx, client, ref)
    if template_id is None:
        return

    try:
        client.delete(f"{_EP}/{template_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Workbook template {template_id} deleted.")
