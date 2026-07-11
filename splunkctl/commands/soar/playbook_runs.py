"""SOAR playbook runs — run, list, get, cancel."""

from __future__ import annotations

import json
import time
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar.playbooks import playbooks_group
from splunkctl.soar.client import SOARClient, SOARError

# Terminal statuses — stop polling when we see one of these.
_TERMINAL: frozenset[str] = frozenset({"success", "failed", "cancelled"})

_DEFAULT_POLL_INTERVAL: float = 2.0
_DEFAULT_TIMEOUT: int = 300


# -- run ---------------------------------------------------------------------


def _resolve_playbook_id(
    client: SOARClient,
    playbook: str,
) -> int | None:
    """Resolve a playbook name to its numeric id.

    Returns the id on success, or None if no match was found.
    """
    params: dict[str, Any] = {
        "_filter_name": f'"{playbook}"',
        "page_size": 1,
    }
    try:
        result = client.get("playbook", params=params)
    except SOARError:
        return None
    data = result.get("data", []) if isinstance(result, dict) else []
    if data and isinstance(data[0], dict):
        return int(data[0]["id"])
    return None


def _build_run_body(
    *,
    playbook_id: int,
    container_id: int,
    scope: str,
    inputs: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble playbook_run POST body."""
    body: dict[str, Any] = {
        "playbook_id": playbook_id,
        "container_id": container_id,
        "scope": scope,
        "run": True,
    }
    if inputs:
        parsed: dict[str, str] = {}
        for item in inputs:
            key, _, value = item.partition("=")
            if key and value:
                parsed[key] = value
        if parsed:
            body["inputs"] = parsed
    return body


def _poll_run(
    client: SOARClient,
    run_id: int,
    *,
    timeout: int,
    interval: float = _DEFAULT_POLL_INTERVAL,
) -> dict[str, Any]:
    """Poll playbook_run until terminal status or timeout.

    Returns the final run dict. Raises SOARError on timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = client.get(f"playbook_run/{run_id}", params={})
        status = result.get("status", "") if isinstance(result, dict) else ""
        if status in _TERMINAL:
            return result if isinstance(result, dict) else {}
        if time.monotonic() > deadline:
            raise SOARError(
                f"Playbook run {run_id} timed out after {timeout}s "
                f"(last status: {status})",
                kind="timeout",
            )
        time.sleep(interval)


def _pretty_message(message: str) -> str:
    """Try to parse *message* as JSON and pretty-print it."""
    try:
        parsed = json.loads(message)
        return json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        return message


@playbooks_group.command("run")
@guard.guarded
@click.argument("playbook")
@click.option(
    "--container",
    "container_id",
    required=True,
    type=int,
    help="Container id.",
)
@click.option(
    "--scope",
    default="all",
    type=click.Choice(["all", "new"]),
    help="Artifact scope (default: all).",
)
@click.option(
    "--input",
    "inputs",
    multiple=True,
    help="Input key=value (repeatable).",
)
@click.option("--wait", "wait_", is_flag=True, help="Poll until terminal status.")
@click.option(
    "--timeout",
    "timeout",
    type=int,
    default=_DEFAULT_TIMEOUT,
    help=f"Wait timeout in seconds (default: {_DEFAULT_TIMEOUT}).",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    playbook: str,
    *,
    container_id: int,
    scope: str,
    inputs: tuple[str, ...],
    wait_: bool,
    timeout: int,
) -> None:
    """Run a playbook against a container.

    PLAYBOOK can be a numeric id or a playbook name.
    """
    # Resolve playbook name -> id if not numeric.
    if playbook.isdigit():
        playbook_id = int(playbook)
        playbook_label = f"playbook id={playbook_id}"
    else:
        playbook_label = f"playbook '{playbook}'"
        playbook_id = -1  # resolved after guard

    body = _build_run_body(
        playbook_id=playbook_id,
        container_id=container_id,
        scope=scope,
        inputs=inputs,
    )
    # Show meaningful placeholder in preview for name-based runs.
    preview_body = body.copy()
    if playbook_id == -1:
        preview_body["playbook_id"] = f"<name: {playbook}>"
    details = json.dumps(preview_body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Run {playbook_label} on container {container_id}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)

    # Resolve name -> id (after guard, since it needs network).
    if not playbook.isdigit():
        resolved = _resolve_playbook_id(client, playbook)
        if resolved is None:
            output.error(
                f"Playbook '{playbook}' not found",
                kind="not_found",
            )
            ctx.exit(1)
            return
        playbook_id = resolved
        body["playbook_id"] = playbook_id

    try:
        result = client.post("playbook_run", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    # SOARClient normalizes playbook_run_id -> id.
    run_id: int | str = "?"
    if isinstance(result, dict):
        raw = result.get("id", "?")
        if isinstance(raw, str) and raw.isdigit():
            run_id = int(raw)
        elif isinstance(raw, int):
            run_id = raw
        else:
            run_id = str(raw) if raw is not None else "?"
    output.info(f"Playbook run started: id={run_id}")

    if not wait_ or not isinstance(run_id, int):
        if isinstance(result, dict):
            output.render(ctx, result)
        return

    # Poll to terminal status.
    output.info("Waiting for completion...")
    try:
        final = _poll_run(client, run_id, timeout=timeout)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind)
        ctx.exit(1)
        return

    final_status = final.get("status", "unknown")
    msg_raw = final.get("message", "")
    msg_display = _pretty_message(msg_raw) if msg_raw else ""

    if final_status in ("failed", "cancelled"):
        output.error(
            f"Playbook run {run_id} {final_status}",
            kind="error",
        )
        if msg_display:
            output.info(f"Message:\n{msg_display}")
        output.render(ctx, final)
        ctx.exit(1)
        return

    output.info(f"Playbook run {run_id} completed: {final_status}")
    if msg_display:
        output.info(f"Message:\n{msg_display}")
    output.render(ctx, final)


# -- runs group --------------------------------------------------------------


@playbooks_group.group("runs")
def runs_group() -> None:
    """Playbook run inspection and management."""


@runs_group.command("list")
@click.option(
    "--container",
    "container_id",
    default=None,
    type=int,
    help="Filter by container id.",
)
@click.option(
    "--status",
    default=None,
    help="Filter by status (pending/running/success/failed).",
)
@click.option(
    "--limit",
    default=None,
    type=click.IntRange(min=1),
    help="Page size.",
)
@click.pass_context
def runs_list_cmd(
    ctx: click.Context,
    *,
    container_id: int | None,
    status: str | None,
    limit: int | None,
) -> None:
    """List playbook runs with optional filters."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {}
    if container_id is not None:
        params["_filter_container"] = container_id
    if status is not None:
        params["_filter_status"] = f'"{status}"'
    if limit is not None:
        params["page_size"] = limit

    try:
        result = client.get("playbook_run", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No playbook runs found.")


@runs_group.command("get")
@click.argument("run_id", type=int)
@click.option("--blocks", is_flag=True, help="Show block results.")
@click.pass_context
def runs_get_cmd(
    ctx: click.Context,
    *,
    run_id: int,
    blocks: bool,
) -> None:
    """Get a playbook run by ID."""
    client = get_soar_client(ctx)

    if blocks:
        path = f"playbook_run/{run_id}/block_results"
    else:
        path = f"playbook_run/{run_id}"

    try:
        result = client.get(path, params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if blocks:
        data = result.get("data", []) if isinstance(result, dict) else []
        output.render(ctx, data, empty=f"No block results for run {run_id}.")
    else:
        if isinstance(result, dict):
            output.render(ctx, result)


@runs_group.command("cancel")
@guard.guarded
@click.argument("run_id", type=int)
@click.pass_context
def runs_cancel_cmd(ctx: click.Context, *, run_id: int) -> None:
    """Cancel a running playbook run."""
    if not guard.soar_check(ctx, f"Cancel playbook run {run_id}"):
        return

    client = get_soar_client(ctx)

    try:
        client.post(f"playbook_run/{run_id}", body={"cancel": True})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook run {run_id} cancelled.")
