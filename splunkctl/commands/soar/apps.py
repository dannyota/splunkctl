"""SOAR app reads — list installed/staged apps, get config schema."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError


@click.group("apps")
def apps_group() -> None:
    """App catalog — list, get (config schema + actions)."""


@apps_group.command("list")
@click.option(
    "--installed",
    is_flag=True,
    default=False,
    help="Only installed apps (exclude staged).",
)
@click.option("--category", default=None, help="Filter by app category.")
@click.option(
    "--limit",
    default=None,
    type=click.IntRange(min=1),
    help="Page size.",
)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    installed: bool,
    category: str | None,
    limit: int | None,
) -> None:
    """List SOAR apps. Use --installed to exclude staged (uninstalled) apps."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {}
    if installed:
        params["_exclude_install_status"] = '"staged"'
    if category is not None:
        params["_filter_category"] = f'"{category}"'
    if limit is not None:
        params["page_size"] = limit

    try:
        result = client.get("app", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No apps found.")


@apps_group.command("get")
@click.argument("app_id", type=int)
@click.option(
    "--actions",
    is_flag=True,
    default=False,
    help="Include supported actions.",
)
@click.pass_context
def get_cmd(
    ctx: click.Context,
    *,
    app_id: int,
    actions: bool,
) -> None:
    """Get an app by ID — config schema, and optionally supported actions."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"app/{app_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if not isinstance(result, dict):
        output.render(ctx, [], empty=f"No app {app_id} found.")
        return

    if actions:
        try:
            actions_resp = client.get(f"app/{app_id}/actions", params={})
            action_data = (
                actions_resp.get("data", []) if isinstance(actions_resp, dict) else []
            )
            result["actions"] = action_data
        except SOARError as exc:
            output.warning(f"could not fetch actions ({exc.message})")

    output.render(ctx, result)
