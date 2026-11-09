"""SOAR playbook lifecycle — enable, disable, and trigger."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar.playbooks import playbooks_group
from splunkctl.soar.client import SOARError


def _mutation_error(exc: SOARError) -> str:
    message = exc.message
    if exc.http_status == 404:
        message += (
            " (hint: a forced import creates a new playbook id; the old id is a "
            "read-only previous version. Find the current id with soar playbooks list)"
        )
    return message


# ─── enable / disable ────────────────────────────────────────────────


@playbooks_group.command("enable")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.pass_context
def enable_cmd(ctx: click.Context, *, playbook_id: int) -> None:
    """Activate a playbook. draft_mode playbooks cannot be activated."""
    body: dict[str, Any] = {"active": True}
    if not guard.soar_check(ctx, f"Enable playbook {playbook_id}"):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        msg = _mutation_error(exc)
        if "draft" in msg.lower():
            msg += (
                " (hint: playbooks in draft_mode cannot be activated; "
                "re-import without draft_mode or edit in the VPE)"
            )
        output.error(msg, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} enabled.")


@playbooks_group.command("disable")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.option(
    "--cancel-runs",
    is_flag=True,
    default=False,
    help="Cancel running instances.",
)
@click.pass_context
def disable_cmd(
    ctx: click.Context,
    *,
    playbook_id: int,
    cancel_runs: bool,
) -> None:
    """Deactivate a playbook. --cancel-runs stops running instances."""
    body: dict[str, Any] = {"active": False}
    action = f"Disable playbook {playbook_id}"
    if cancel_runs:
        # The destructive side effect must be visible in the preview.
        body["cancel_runs"] = True
        action += " (cancel in-flight runs)"
    if not guard.soar_check(ctx, action):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        output.error(_mutation_error(exc), kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} disabled.")


# ─── trigger ──────────────────────────────────────────────────────────


@playbooks_group.command("trigger")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.option(
    "--on",
    "trigger_type",
    required=True,
    type=click.Choice(["artifact_created", "container_resolved"]),
    help=(
        "Trigger type. ('label' is import-metadata only — the REST "
        "endpoint rejects setting it.)"
    ),
)
@click.pass_context
def trigger_cmd(
    ctx: click.Context,
    *,
    playbook_id: int,
    trigger_type: str,
) -> None:
    """Set the automation trigger for a playbook."""
    body: dict[str, Any] = {"playbook_trigger": trigger_type}
    if not guard.soar_check(
        ctx, f"Set trigger '{trigger_type}' for playbook {playbook_id}"
    ):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        output.error(_mutation_error(exc), kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} trigger set to '{trigger_type}'.")
