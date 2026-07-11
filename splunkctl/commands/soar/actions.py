"""SOAR actions — run, list, status, results, cancel."""

from __future__ import annotations

import json
import time
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError

_TERMINAL_STATUSES: frozenset[str] = frozenset({"success", "failed"})
_DEFAULT_POLL_INTERVAL: float = 2.0
_DEFAULT_TIMEOUT: int = 300


@click.group("actions")
def actions_group() -> None:
    """Action runs — execute, poll, inspect, cancel."""


# -- list ------------------------------------------------------------------


@actions_group.command("list")
@click.option(
    "--container",
    "container_id",
    default=None,
    type=int,
    help="Container id to scope results.",
)
@click.option("--limit", default=None, type=int, help="Max results.")
@click.option("--offset", default=0, type=int, help="Paging offset.")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    container_id: int | None,
    limit: int | None,
    offset: int,
) -> None:
    """List action runs (optionally scoped to a container)."""
    client = get_soar_client(ctx)

    if container_id is not None:
        path = f"container/{container_id}/actions"
    else:
        path = "action_run"

    params: dict[str, Any] = {"page": 0}
    if limit is not None:
        params["page_size"] = limit
    if offset:
        params["page"] = offset

    try:
        result = client.get(path, params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No action runs found.")


# -- status ----------------------------------------------------------------


@actions_group.command("status")
@click.argument("action_run_id", type=int)
@click.pass_context
def status_cmd(ctx: click.Context, action_run_id: int) -> None:
    """Get status of an action run."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"action_run/{action_run_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)


# -- results ---------------------------------------------------------------


@actions_group.command("results")
@click.argument("action_run_id", type=int)
@click.pass_context
def results_cmd(ctx: click.Context, action_run_id: int) -> None:
    """Get per-asset detail (app_runs) for an action run."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"action_run/{action_run_id}/app_runs", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No app_run results.")


# -- run -------------------------------------------------------------------


def _parse_params(raw: tuple[str, ...]) -> dict[str, str]:
    """Parse ``key=value`` pairs into a parameters dict."""
    params: dict[str, str] = {}
    for pair in raw:
        key, _, value = pair.partition("=")
        if key:
            params[key] = value
    return params


def _resolve_app_id(
    client: Any,
    asset_name: str,
) -> int | None:
    """Look up app_id from asset name via ``/rest/asset``.

    The SOAR asset record stores the app reference as ``app`` (not
    ``app_id``). Falls back to ``app_id`` for forward-compatibility.
    """
    try:
        result = client.get(
            "asset",
            params={"_filter_name": f'"{asset_name}"', "page_size": 1},
        )
    except SOARError:
        return None
    data = result.get("data", []) if isinstance(result, dict) else []
    if data and isinstance(data[0], dict):
        aid = data[0].get("app") or data[0].get("app_id") or 0
        return int(aid) if aid else None
    return None


def _build_targets(
    client: Any,
    assets: tuple[str, ...],
    app_id: int | None,
    params: dict[str, str],
) -> tuple[list[dict[str, Any]], str | None]:
    """Build the targets list for action_run POST.

    Returns (targets, error_msg). Groups assets by app_id.
    """
    if not assets:
        return [], "At least one --asset is required."

    params_list: list[dict[str, str]] = [params] if params else []

    if app_id is not None:
        # Explicit app_id — no lookup needed
        target: dict[str, Any] = {
            "app_id": app_id,
            "assets": list(assets),
            "parameters": params_list,
        }
        return [target], None

    # Resolve app_id per asset, group by app_id
    grouped: dict[int, list[str]] = {}
    for name in assets:
        resolved = _resolve_app_id(client, name)
        if resolved is None or resolved == 0:
            return [], f"Asset '{name}' not found or has no app_id."
        grouped.setdefault(resolved, []).append(name)

    targets: list[dict[str, Any]] = []
    for aid, names in grouped.items():
        targets.append(
            {
                "app_id": aid,
                "assets": names,
                "parameters": params_list,
            }
        )
    return targets, None


def _poll_action(
    client: Any,
    action_run_id: int,
    *,
    timeout: int,
) -> dict[str, Any] | None:
    """Poll action_run status until terminal or timeout.

    Returns the final status dict, or None on timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            status: dict[str, Any] = client.get(
                f"action_run/{action_run_id}",
                params={},
            )
        except SOARError:
            return None

        current = status.get("status", "") if isinstance(status, dict) else ""
        if current in _TERMINAL_STATUSES:
            return status

        if time.monotonic() > deadline:
            return None

        time.sleep(_DEFAULT_POLL_INTERVAL)


@actions_group.command("run")
@guard.guarded
@click.option("--action", "action_name", required=True, help="Action name.")
@click.option(
    "--asset",
    "assets",
    multiple=True,
    required=True,
    help="Asset name (repeatable).",
)
@click.option(
    "--app",
    "app_id",
    default=None,
    type=int,
    help="Explicit app id (skips asset lookup).",
)
@click.option(
    "--container",
    "container_id",
    required=True,
    type=int,
    help="Container id.",
)
@click.option(
    "--param",
    "params_raw",
    multiple=True,
    help="Action parameter key=value (repeatable).",
)
@click.option(
    "--type",
    "action_type",
    default="investigate",
    help="Action type (default: investigate).",
)
@click.option(
    "--name",
    "run_name",
    default=None,
    help="Run name (defaults to action name).",
)
@click.option("--wait", is_flag=True, help="Poll until the action completes.")
@click.option(
    "--timeout",
    default=_DEFAULT_TIMEOUT,
    type=int,
    help=f"Wait timeout in seconds (default: {_DEFAULT_TIMEOUT}).",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    *,
    action_name: str,
    assets: tuple[str, ...],
    app_id: int | None,
    container_id: int,
    params_raw: tuple[str, ...],
    action_type: str,
    run_name: str | None,
    wait: bool,
    timeout: int,
) -> None:
    """Run an action on one or more assets within a container."""
    params = _parse_params(params_raw)
    run_name = run_name or action_name

    # Build a preview payload for guard
    preview: dict[str, Any] = {
        "action": action_name,
        "container_id": container_id,
        "name": run_name,
        "type": action_type,
        "targets": [
            {
                "app_id": app_id or "<resolved from asset>",
                "assets": list(assets),
                "parameters": [params] if params else [],
            }
        ],
    }
    details = json.dumps(preview, indent=2)
    if not guard.soar_check(ctx, f"Run action '{action_name}'", details=details):
        return

    client = get_soar_client(ctx)

    targets, err = _build_targets(client, assets, app_id, params)
    if err:
        output.error(err, kind="usage")
        ctx.exit(1)
        return

    body: dict[str, Any] = {
        "action": action_name,
        "container_id": container_id,
        "name": run_name,
        "targets": targets,
        "type": action_type,
    }

    try:
        result = client.post("action_run", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Action run created: id={new_id}")

    if not wait or new_id == "?":
        if isinstance(result, dict):
            output.render(ctx, result)
        return

    # Poll until terminal
    output.info(f"Waiting for action run {new_id} (timeout={timeout}s)...")
    final = _poll_action(client, int(new_id), timeout=timeout)

    if final is None:
        output.error(
            f"Action run {new_id} did not complete within {timeout}s.",
            kind="timeout",
        )
        ctx.exit(1)
        return

    final_status = final.get("status", "unknown")
    output.info(f"Action run {new_id}: {final_status}")

    # Always fetch app_runs for detail
    try:
        app_runs = client.get(f"action_run/{new_id}/app_runs", params={})
        data = app_runs.get("data", []) if isinstance(app_runs, dict) else []
        if data:
            output.render(ctx, data)
        else:
            output.render(ctx, final)
    except SOARError:
        output.render(ctx, final)

    if final_status == "failed":
        ctx.exit(1)


# -- cancel ----------------------------------------------------------------


@actions_group.command("cancel")
@guard.guarded
@click.argument("action_run_id", type=int)
@click.pass_context
def cancel_cmd(ctx: click.Context, action_run_id: int) -> None:
    """Cancel a running action."""
    if not guard.soar_check(ctx, f"Cancel action run {action_run_id}"):
        return

    client = get_soar_client(ctx)

    try:
        client.post(f"action_run/{action_run_id}", body={"cancel": True})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Action run {action_run_id} cancelled.")
