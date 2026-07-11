"""SOAR notes and comments — list, add, delete notes; add comments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import guarded, soar_check
from splunkctl.soar.client import SOARError


@click.group("notes")
def notes_group() -> None:
    """Notes and comments on SOAR containers."""


# ---------------------------------------------------------------------------
# notes list
# ---------------------------------------------------------------------------


@notes_group.command("list")
@click.option(
    "--container",
    required=True,
    type=int,
    help="Container ID to list notes for.",
)
@click.option(
    "--task",
    default=None,
    type=int,
    help="Filter to notes on a specific task ID.",
)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    container: int,
    task: int | None,
) -> None:
    """List notes for a container, optionally filtered by task."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {}
    if task is not None:
        # Task notes aren't visible on the container sub-view;
        # query the note collection with container + task_id filters.
        path = "note"
        params["_filter_container"] = container
        params["_filter_task_id"] = task
    else:
        path = f"container/{container}/notes"

    try:
        result = client.get(path, params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty=f"No notes for container {container}.")


# ---------------------------------------------------------------------------
# notes add
# ---------------------------------------------------------------------------


@notes_group.command("add")
@click.option(
    "--container",
    required=True,
    type=int,
    help="Container ID to attach the note to.",
)
@click.option("--title", required=True, help="Note title.")
@click.option(
    "--task-id",
    default=None,
    type=int,
    help="Task ID — makes this a task note instead of a general note.",
)
@click.option(
    "--file",
    "file_path",
    default=None,
    type=click.Path(exists=True),
    help="Read content from a file instead of the positional argument.",
)
@click.argument("content", required=False, default=None)
@click.pass_context
@guarded
def add_cmd(
    ctx: click.Context,
    *,
    container: int,
    title: str,
    task_id: int | None,
    file_path: str | None,
    content: str | None,
) -> None:
    """Add a note to a container (markdown format).

    Content is taken from the positional argument or --file.
    """
    # Resolve content
    if file_path is not None:
        resolved_content = Path(file_path).read_text()
    elif content is not None:
        resolved_content = content
    else:
        output.error(
            "Provide content as an argument or via --file.",
            kind="usage",
        )
        ctx.exit(1)
        return

    note_type = "task" if task_id is not None else "general"
    body: dict[str, Any] = {
        "container_id": container,
        "title": title,
        "content": resolved_content,
        "note_type": note_type,
    }
    if task_id is not None:
        body["task_id"] = task_id

    details = (
        f"  container: {container}\n"
        f"  title:     {title}\n"
        f"  type:      {note_type}\n"
        f"  content:   {resolved_content[:80]}"
        f"{'...' if len(resolved_content) > 80 else ''}"
    )
    if not soar_check(ctx, f"Add note to container {container}", details=details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("note", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)


# ---------------------------------------------------------------------------
# notes delete
# ---------------------------------------------------------------------------


@notes_group.command("delete")
@click.argument("note_id", type=int)
@click.pass_context
@guarded
def delete_cmd(ctx: click.Context, *, note_id: int) -> None:
    """Delete a note by ID."""
    if not soar_check(ctx, f"Delete note {note_id}"):
        return

    client = get_soar_client(ctx)
    try:
        result = client.delete(f"note/{note_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result if isinstance(result, dict) else {"id": note_id})


# ---------------------------------------------------------------------------
# comment add
# ---------------------------------------------------------------------------


@notes_group.command("comment")
@click.argument("container_id", type=int)
@click.argument("text")
@click.pass_context
@guarded
def comment_cmd(ctx: click.Context, *, container_id: int, text: str) -> None:
    """Add a comment to a container (immutable — cannot be deleted)."""
    details = (
        f"  container: {container_id}\n"
        f"  comment:   {text[:80]}{'...' if len(text) > 80 else ''}"
    )
    if not soar_check(ctx, f"Add comment to container {container_id}", details=details):
        return

    client = get_soar_client(ctx)
    body: dict[str, Any] = {
        "container_id": container_id,
        "comment": text,
    }
    try:
        result = client.post("container_comment", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)


# ---------------------------------------------------------------------------
# comment-delete — immutability explanation
# ---------------------------------------------------------------------------


@notes_group.command("comment-delete")
@click.argument("comment_id", type=int, expose_value=False)
@click.pass_context
def comment_delete_cmd(ctx: click.Context) -> None:
    """Attempt to delete a comment — explains immutability."""
    output.error(
        "SOAR comments are immutable and cannot be deleted. "
        "Comments are removed only when the parent container is deleted.",
        kind="usage",
    )
    ctx.exit(1)
