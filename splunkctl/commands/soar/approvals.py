"""SOAR approvals: list, get, and respond to approval requests.

Approvals are created by playbook prompt blocks. A paused playbook waits
for an external approve/deny response before continuing. This module
surfaces pending approvals and lets an operator respond from the terminal,
unblocking automation without switching to the SOAR UI.

Endpoints:
- ``GET /rest/approval``: list all approvals
- ``GET /rest/container/<id>/approvals``: per-container approvals
- ``GET /rest/approval/<id>?_detail=detail_summary_view``: detail view
- ``POST /rest/approval/<id>``: respond with ``{status, message,
  responses}``; SOAR requires a message or responses (verified live on
  8.8.0.282; ``/rest/external_prompt/<id>`` is only for secure-link
  prompts and returns 404 for an approval id)
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
    help="Response message. SOAR requires --message or --response.",
)
@click.option(
    "--response",
    "responses",
    multiple=True,
    help="Answer to a prompt question, in question order (repeatable).",
)
@click.pass_context
def respond_cmd(
    ctx: click.Context,
    *,
    approval_id: int,
    action: str,
    message: str | None,
    responses: tuple[str, ...],
) -> None:
    """Respond to an approval request (approve or deny).

    Posts to ``/rest/approval/<id>``. SOAR rejects a response without a
    message or prompt answers, so pass ``--message`` or ``--response``.
    Guarded: dry-run by default, pass ``--yes`` to apply.
    """
    if not message and not responses:
        raise click.UsageError("Pass --message or --response; SOAR requires one.")
    action = action.lower()
    details = f"  approval: {approval_id}\n  action:   {action}"
    if message:
        details += f"\n  message:  {message[:80]}{'...' if len(message) > 80 else ''}"
    if responses:
        details += f"\n  responses: {list(responses)}"

    if not soar_check(
        ctx, f"Respond to approval {approval_id}: {action}", details=details
    ):
        return

    body: dict[str, Any] = {"status": action}
    if message:
        body["message"] = message
    if responses:
        body["responses"] = list(responses)

    client = get_soar_client(ctx)
    try:
        result = client.post(f"approval/{approval_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)
