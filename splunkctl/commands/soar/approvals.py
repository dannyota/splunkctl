"""SOAR approvals — list, get, and respond to approval requests.

Approvals are created by playbook prompt blocks. A paused playbook waits
for an external approve/deny response before continuing. This module
surfaces pending approvals and lets an operator respond from the terminal,
unblocking automation without switching to the SOAR UI.

Endpoints:
- ``GET /rest/approval`` — list all approvals
- ``GET /rest/container/<id>/approvals`` — per-container approvals
- ``GET /rest/approval/<id>?_detail=detail_summary_view`` — detail view
- ``POST /rest/external_prompt/<id>`` — respond (approve/deny)
"""

from __future__ import annotations

from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import guarded, soar_check
from splunkctl.soar.client import SOARError


@click.group("approvals")
def approvals_group() -> None:
    """Approval requests from SOAR playbook prompts."""


# ---------------------------------------------------------------------------
# approvals list
# ---------------------------------------------------------------------------


@approvals_group.command("list")
@click.option(
    "--container",
    default=None,
    type=int,
    help="Filter approvals to a specific container ID.",
)
@click.option(
    "--pending",
    is_flag=True,
    default=False,
    help="Show only pending (unanswered) approvals.",
)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    container: int | None,
    pending: bool,
) -> None:
    """List approval requests, optionally filtered by container or status."""
    client = get_soar_client(ctx)

    path = f"container/{container}/approvals" if container else "approval"
    params: dict[str, Any] = {}
    if pending:
        params["_filter_status"] = '"pending"'

    try:
        result = client.get(path, params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No approvals found.")


# ---------------------------------------------------------------------------
# approvals get
# ---------------------------------------------------------------------------


@approvals_group.command("get")
@click.argument("approval_id", type=int)
@click.pass_context
def get_cmd(ctx: click.Context, *, approval_id: int) -> None:
    """Get approval detail (summary view) by ID."""
    client = get_soar_client(ctx)

    try:
        result = client.get(
            f"approval/{approval_id}",
            params={"_detail": "detail_summary_view"},
        )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)


# ---------------------------------------------------------------------------
# approvals respond
# ---------------------------------------------------------------------------


@approvals_group.command("respond")
@guarded
@click.argument("approval_id", type=int)
@click.argument(
    "action",
    type=click.Choice(["approve", "deny"], case_sensitive=False),
)
@click.option(
    "--message",
    default=None,
    help="Optional response message.",
)
@click.pass_context
def respond_cmd(
    ctx: click.Context,
    *,
    approval_id: int,
    action: str,
    message: str | None,
) -> None:
    """Respond to an approval request (approve or deny).

    Posts to ``/rest/external_prompt/<id>`` with the chosen action.
    Guarded: dry-run by default, pass ``--yes`` to apply.
    """
    details = f"  approval: {approval_id}\n  action:   {action}"
    if message:
        details += f"\n  message:  {message[:80]}{'...' if len(message) > 80 else ''}"

    if not soar_check(
        ctx, f"Respond to approval {approval_id}: {action}", details=details
    ):
        return

    body: dict[str, Any] = {"status": action}
    if message:
        body["message"] = message

    client = get_soar_client(ctx)
    try:
        result = client.post(f"external_prompt/{approval_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)
