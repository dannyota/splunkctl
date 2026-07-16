"""SOAR app management — list, get, install, uninstall."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError


@click.group("apps")
def apps_group() -> None:
    """App catalog — list, get, install, uninstall."""


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
        params["_filter_category"] = json.dumps(category)
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


# ─── install ─────────────────────────────────────────────────────────


@apps_group.command("install")
@guard.guarded
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def install_cmd(ctx: click.Context, *, path: str) -> None:
    """Install a SOAR app from a tgz package.

    PATH is a local .tgz file exported from the Splunk SOAR app store or
    built by the app developer. The file is base64-encoded and POSTed to
    ``/rest/app``, similar to playbook imports.
    """
    src = Path(path)
    if not src.is_file():
        output.error(f"Expected a file, got: {path}", kind="usage")
        ctx.exit(1)
        return

    tgz_bytes = src.read_bytes()
    encoded = base64.b64encode(tgz_bytes).decode()

    if not guard.soar_check(ctx, f"Install app from '{src.name}'"):
        return

    client = get_soar_client(ctx)
    body: dict[str, Any] = {"app": encoded}
    try:
        result = client.post("app", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"App installed: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


# ─── uninstall ───────────────────────────────────────────────────────


def _resolve_app_id(
    ctx: click.Context,
    client: Any,
    ref: str,
) -> int | None:
    """Resolve an app name or numeric id to a numeric id.

    Returns None and emits an error if the app cannot be found.
    """
    if ref.isascii() and ref.isdigit():
        return int(ref)

    try:
        result = client.get("app", params={"_filter_name": json.dumps(ref)})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return None

    data = result.get("data", []) if isinstance(result, dict) else []
    if not data:
        output.error(f"App '{ref}' not found.", kind="not_found")
        ctx.exit(1)
        return None
    if len(data) >= 2:
        output.error(
            f"Ambiguous: multiple apps named '{ref}'",
            kind="ambiguous",
        )
        ctx.exit(1)
        return None
    return int(data[0]["id"])


@apps_group.command("uninstall")
@guard.guarded
@click.argument("ref")
@click.pass_context
def uninstall_cmd(ctx: click.Context, *, ref: str) -> None:
    """Uninstall a SOAR app by name or id.

    Uses DELETE /rest/app/<id>. SOAR refuses token auth on DELETE,
    so username/password credentials must be configured.
    """
    if not guard.soar_check(ctx, f"Uninstall app '{ref}'"):
        return

    client = get_soar_client(ctx)
    app_id = _resolve_app_id(ctx, client, ref)
    if app_id is None:
        return

    try:
        client.delete(f"app/{app_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"App {app_id} uninstalled.")
