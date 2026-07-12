"""SOAR cases — promote, workbook view, phase/task management."""

from __future__ import annotations

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError

# Task status: the SOAR API uses integers internally.
_STATUS_MAP: dict[str, int] = {
    "incomplete": 0,
    "in_progress": 1,
    "complete": 2,
}

# Status 1 (in_progress) requires a closing note — the server rejects the
# transition without one ("Closing note content is required").
_NOTE_REQUIRED_STATUSES: frozenset[int] = frozenset({1})


# -- Top-level group --------------------------------------------------------


@click.group("cases")
def cases_group() -> None:
    """Case management — promote, workbook phases & tasks."""


# -- promote ----------------------------------------------------------------


def _resolve_template(
    client: Any,
    template_arg: str | None,
) -> int:
    """Resolve a workbook template name or id to an integer id.

    When *template_arg* is ``None``, returns the ``is_default`` template.
    Raises ``click.ClickException`` on failure.
    """
    try:
        result = client.get("workbook_template", params={})
    except SOARError as exc:
        raise click.ClickException(
            f"Could not fetch workbook templates: {exc.message}"
        ) from exc

    data: list[dict[str, Any]] = []
    if isinstance(result, dict):
        data = result.get("data", [])

    if not data:
        raise click.ClickException("No workbook templates available on this instance.")

    # Numeric id?
    if template_arg is not None and template_arg.isascii() and template_arg.isdigit():
        tid = int(template_arg)
        if any(t.get("id") == tid for t in data):
            return tid
        names = ", ".join(t.get("name", "?") for t in data)
        raise click.ClickException(f"Template id {tid} not found. Available: {names}")

    # Name match (case-sensitive)?
    if template_arg is not None:
        for t in data:
            if t.get("name") == template_arg:
                return int(t["id"])
        names = ", ".join(t.get("name", "?") for t in data)
        raise click.ClickException(
            f"Template '{template_arg}' not found. Available: {names}"
        )

    # Default template.
    for t in data:
        if t.get("is_default"):
            return int(t["id"])

    names = ", ".join(t.get("name", "?") for t in data)
    raise click.ClickException(
        f"No default workbook template found. Specify --template. Available: {names}"
    )


@cases_group.command("promote")
@guard.guarded
@click.argument("container_id", type=int)
@click.option(
    "--template",
    "template_arg",
    default=None,
    help="Workbook template name or id (default: server default).",
)
@click.pass_context
def promote_cmd(
    ctx: click.Context,
    *,
    container_id: int,
    template_arg: str | None,
) -> None:
    """Promote a container to a case with a workbook template."""
    client = get_soar_client(ctx)
    template_id = _resolve_template(client, template_arg)

    body: dict[str, Any] = {
        "container_type": "case",
        "template": template_id,
    }
    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Promote container {container_id} to case",
        details=details,
    ):
        return

    try:
        result = client.post(f"container/{container_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Container {container_id} promoted to case.")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


# -- workbook ---------------------------------------------------------------


@cases_group.command("workbook")
@click.argument("container_id", type=int)
@click.pass_context
def workbook_cmd(ctx: click.Context, *, container_id: int) -> None:
    """Show workbook phases and nested tasks for a case."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"container/{container_id}/phases", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data: list[dict[str, Any]] = []
    if isinstance(result, dict):
        data = result.get("data", [])
    elif isinstance(result, list):
        data = result

    output.render(ctx, data, empty=f"No phases for container {container_id}.")


# -- phase subgroup ---------------------------------------------------------


@cases_group.group("phase")
def phase_group() -> None:
    """Workbook phase management."""


@phase_group.command("add")
@guard.guarded
@click.option(
    "--container", "container_id", required=True, type=int, help="Container id."
)
@click.option("--name", required=True, help="Phase name.")
@click.option("--order", default=None, type=int, help="Display order.")
@click.pass_context
def phase_add_cmd(
    ctx: click.Context,
    *,
    container_id: int,
    name: str,
    order: int | None,
) -> None:
    """Add a phase to a case workbook."""
    body: dict[str, Any] = {"container_id": container_id, "name": name}
    if order is not None:
        body["order"] = order

    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Add phase '{name}' to container {container_id}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("workbook_phase", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Phase created: id={new_id}")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


# -- task subgroup ----------------------------------------------------------


@cases_group.group("task")
def task_group() -> None:
    """Workbook task management."""


@task_group.command("add")
@guard.guarded
@click.option("--phase-id", required=True, type=int, help="Phase id.")
@click.option("--name", required=True, help="Task name.")
@click.option("--description", default=None, help="Task description.")
@click.option("--order", default=None, type=int, help="Display order.")
@click.pass_context
def task_add_cmd(
    ctx: click.Context,
    *,
    phase_id: int,
    name: str,
    description: str | None,
    order: int | None,
) -> None:
    """Add a task to a workbook phase."""
    body: dict[str, Any] = {"phase_id": phase_id, "name": name}
    if description is not None:
        body["description"] = description
    if order is not None:
        body["order"] = order

    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Add task '{name}' to phase {phase_id}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("workbook_task", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Task created: id={new_id}")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


@task_group.command("update")
@guard.guarded
@click.argument("task_id", type=int)
@click.option(
    "--status",
    type=click.Choice(["incomplete", "in_progress", "complete"]),
    default=None,
    help="Task status (mapped to integer codes).",
)
@click.option("--owner", default=None, help="Task owner username.")
@click.option("--note", default=None, help="Closing note (required for in_progress).")
@click.pass_context
def task_update_cmd(
    ctx: click.Context,
    *,
    task_id: int,
    status: str | None,
    owner: str | None,
    note: str | None,
) -> None:
    """Update a workbook task — status, owner, closing note."""
    # Client-side validation: in_progress requires a closing note.
    if status is not None and _STATUS_MAP[status] in _NOTE_REQUIRED_STATUSES:
        if note is None:
            output.error(
                f"Status '{status}' requires a closing note. "
                "The SOAR server demands 'Closing note content is required' "
                'for this transition. Pass --note "<reason>".',
                kind="usage",
            )
            ctx.exit(1)
            return

    body: dict[str, Any] = {}
    if status is not None:
        body["status"] = _STATUS_MAP[status]
        if note is not None:
            # The server wants the closing note INLINE with the status
            # transition (field name: singular ``note``) — a separate
            # note POST arrives too late, the transition itself is
            # rejected without it. The inline note still lands as a
            # regular task note object.
            body["note"] = note
    if owner is not None:
        body["owner"] = owner

    if not body and note is None:
        output.error(
            "No updates specified. Use --status, --owner, or --note.",
            kind="usage",
        )
        ctx.exit(1)
        return

    details = json.dumps(body, indent=2)
    if note:
        details += f'\nnote: "{note}"'
    if not guard.soar_check(
        ctx,
        f"Update task {task_id}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)

    # Post task update if there are field changes.
    if body:
        try:
            client.post(f"workbook_task/{task_id}", body=body)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return

    # Post a standalone note only when it wasn't carried inline above.
    if note is not None and "note" not in body:
        # Fetch the task to get its container_id.
        try:
            task_data = client.get(f"workbook_task/{task_id}", params={})
        except SOARError as exc:
            output.error(
                f"Task updated but note failed — could not fetch task: {exc.message}",
                kind=exc.kind,
                http_status=exc.http_status,
            )
            ctx.exit(1)
            return

        container_id = (
            task_data.get("container") if isinstance(task_data, dict) else None
        )
        if container_id is None:
            output.error(
                "Task updated but note failed — could not determine container_id.",
                kind="api",
            )
            ctx.exit(1)
            return

        note_body: dict[str, Any] = {
            "container_id": int(container_id),
            "content": note,
            "note_type": "general",
            "task_id": task_id,
        }
        try:
            client.post("note", body=note_body)
        except SOARError as exc:
            output.error(
                f"Task updated but note failed: {exc.message}",
                kind=exc.kind,
                http_status=exc.http_status,
            )
            ctx.exit(1)
            return

    output.info(f"Task {task_id} updated.")
