"""SOAR custom lists (decided_list) — CRUD, export, import."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import guarded, soar_check
from splunkctl.soar.client import SOARError

_EP = "decided_list"


def _parse_content_file(path: Path) -> list[list[str]]:
    """Parse a JSON or CSV file into array-of-rows for the decided_list API.

    JSON files must contain a list of lists (``[[col,...],...]``).
    CSV files are parsed row-by-row (header row included as first element).

    Raises:
        click.UsageError: On invalid format or structure.
    """
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".csv":
        reader = csv.reader(io.StringIO(text))
        return [row for row in reader if row]

    # Default: JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"Invalid JSON in {path.name}: {exc}") from exc

    if not isinstance(data, list) or (data and not isinstance(data[0], list)):
        raise click.UsageError(
            f"{path.name} must be a JSON array of arrays "
            '(e.g. [["col1","col2"],["a","b"]])'
        )
    return data


def _resolve_list_id(
    ctx: click.Context,
    client: Any,
    ref: str,
) -> int | None:
    """Resolve a name-or-id reference to a decided_list id.

    Returns the integer id, or None after printing an error.
    """
    if ref.isdigit():
        return int(ref)

    # Name lookup.
    try:
        result = client.get(_EP, params={"_filter_name": f'"{ref}"'})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return None

    data = result.get("data", []) if isinstance(result, dict) else []
    if not data:
        output.error(f"Custom list '{ref}' not found.", kind="not_found")
        ctx.exit(1)
        return None
    return int(data[0]["id"])


@click.group("lists")
def lists_group() -> None:
    """Custom list (decided_list) operations."""


@lists_group.command("list")
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Page size.")
@click.pass_context
def list_cmd(ctx: click.Context, *, limit: int | None) -> None:
    """List all custom lists."""
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
    output.render(ctx, data, empty="No custom lists found.")


@lists_group.command("get")
@click.argument("ref")
@click.pass_context
def get_cmd(ctx: click.Context, *, ref: str) -> None:
    """Get a custom list by name or id (shows rows)."""
    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    try:
        result = client.get(f"{_EP}/{list_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, {}, empty="No data.")


@lists_group.command("create")
@guarded
@click.option("--name", required=True, help="List name.")
@click.option(
    "--file",
    "file_path",
    default=None,
    type=click.Path(exists=True),
    help="JSON or CSV file with rows ([[col,...],...]). CSV parsed client-side.",
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    *,
    name: str,
    file_path: str | None,
) -> None:
    """Create a custom list. Content via --file (JSON or CSV; at least one row)."""
    if file_path is None:
        raise click.UsageError(
            "SOAR requires at least one row — pass --file with at least one row."
        )

    content = _parse_content_file(Path(file_path))
    if not content:
        raise click.UsageError(
            "SOAR requires at least one row — pass --file with at least one row."
        )

    body: dict[str, Any] = {"name": name, "content": content}
    details = f"  name: {name}\n  rows: {len(content)}"
    if not soar_check(ctx, f"Create custom list '{name}'", details=details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post(_EP, body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Custom list created: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


@lists_group.command("update")
@guarded
@click.argument("ref")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True),
    help="JSON or CSV file with full replacement content.",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    *,
    ref: str,
    file_path: str,
) -> None:
    """Replace a list's content (full-replace semantics)."""
    content = _parse_content_file(Path(file_path))

    details = (
        f"  list: {ref}\n"
        f"  rows: {len(content)} (FULL REPLACE — all existing rows will be overwritten)"
    )
    if not soar_check(ctx, f"Update custom list {ref}", details=details):
        return

    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    body: dict[str, Any] = {"content": content}
    try:
        client.post(f"{_EP}/{list_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Custom list {list_id} updated ({len(content)} rows).")


@lists_group.command("add-row")
@guarded
@click.argument("ref")
@click.option(
    "--values",
    required=True,
    help=(
        'Comma-separated values for the new row (e.g. "a,b,c"). '
        "For values containing commas, pass a JSON array "
        '(e.g. \'["a, with comma","b"]\').'
    ),
)
@click.pass_context
def add_row_cmd(
    ctx: click.Context,
    *,
    ref: str,
    values: str,
) -> None:
    """Append a row to a custom list (fetch-modify-replace)."""
    if values.startswith("["):
        try:
            parsed = json.loads(values)
        except json.JSONDecodeError as exc:
            raise click.UsageError(f"Invalid JSON array in --values: {exc}") from exc
        if not isinstance(parsed, list):
            raise click.UsageError("--values JSON must be an array.")
        row = [str(v) for v in parsed]
    else:
        row = [v.strip() for v in values.split(",")]

    details = f"  list: {ref}\n  new row: {row}"
    if not soar_check(ctx, f"Add row to custom list {ref}", details=details):
        return

    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    try:
        current = client.get(f"{_EP}/{list_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    existing: list[list[str]] = (
        current.get("content", []) if isinstance(current, dict) else []
    )
    existing.append(row)

    try:
        client.post(f"{_EP}/{list_id}", body={"content": existing})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Row added to list {list_id}. Total rows: {len(existing)}.")


@lists_group.command("remove-row")
@guarded
@click.argument("ref")
@click.option(
    "--index",
    required=True,
    type=int,
    help="Row index to remove (0-based, within content array).",
)
@click.pass_context
def remove_row_cmd(
    ctx: click.Context,
    *,
    ref: str,
    index: int,
) -> None:
    """Remove a row by index from a custom list (fetch-modify-replace)."""
    details = f"  list: {ref}\n  remove index: {index}"
    action = f"Remove row {index} from custom list {ref}"
    if not soar_check(ctx, action, details=details):
        return

    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    try:
        current = client.get(f"{_EP}/{list_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    existing: list[list[str]] = (
        current.get("content", []) if isinstance(current, dict) else []
    )
    if index < 0 or index >= len(existing):
        output.error(
            f"Row index {index} out of range (list has {len(existing)} rows).",
            kind="usage",
        )
        ctx.exit(1)
        return

    removed = existing.pop(index)
    try:
        client.post(f"{_EP}/{list_id}", body={"content": existing})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Row {index} removed from list {list_id}: {removed}")


@lists_group.command("delete")
@guarded
@click.argument("ref")
@click.pass_context
def delete_cmd(ctx: click.Context, *, ref: str) -> None:
    """Delete a custom list by name or id (token auth allowed)."""
    if not soar_check(ctx, f"Delete custom list {ref}"):
        return

    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    try:
        client.delete(f"{_EP}/{list_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Custom list {list_id} deleted.")


@lists_group.command("export")
@click.argument("ref")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["json", "csv"]),
    help="Export format (default: json).",
)
@click.option("--out", default=None, type=click.Path(), help="Write to file.")
@click.pass_context
def export_cmd(
    ctx: click.Context,
    *,
    ref: str,
    fmt: str | None,
    out: str | None,
) -> None:
    """Export a custom list's content. CSV uses the formatted_content route."""
    client = get_soar_client(ctx)
    list_id = _resolve_list_id(ctx, client, ref)
    if list_id is None:
        return

    if fmt == "csv":
        try:
            raw = client.get_bytes(
                f"{_EP}/{list_id}/formatted_content",
                params={"_output_format": "csv"},
            )
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return

        text = raw.decode("utf-8")
        if out:
            Path(out).write_text(text, encoding="utf-8")
            output.info(f"CSV exported to {out}")
        else:
            click.echo(text, nl=False)
        return

    # Default: JSON — fetch content from the list object.
    try:
        result = client.get(f"{_EP}/{list_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    content = result.get("content", []) if isinstance(result, dict) else []
    text = json.dumps(content, indent=2)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        output.info(f"JSON exported to {out}")
    else:
        click.echo(text)


@lists_group.command("import")
@guarded
@click.option("--name", required=True, help="List name (creates or updates).")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True),
    help="JSON or CSV file with rows.",
)
@click.pass_context
def import_cmd(
    ctx: click.Context,
    *,
    name: str,
    file_path: str,
) -> None:
    """Import a custom list: create if new, update (full-replace) if exists."""
    content = _parse_content_file(Path(file_path))

    # Check if the list already exists.
    details = f"  name: {name}\n  rows: {len(content)}"
    if not soar_check(ctx, f"Import custom list '{name}'", details=details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.get(_EP, params={"_filter_name": f'"{name}"'})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []

    if data:
        # Update existing.
        existing_id = int(data[0]["id"])
        try:
            client.post(f"{_EP}/{existing_id}", body={"content": content})
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(
            f"Custom list '{name}' updated (id={existing_id}, {len(content)} rows)."
        )
    else:
        # Create new.
        body: dict[str, Any] = {"name": name, "content": content}
        try:
            res = client.post(_EP, body=body)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        new_id = res.get("id", "?") if isinstance(res, dict) else "?"
        output.info(f"Custom list '{name}' created (id={new_id}, {len(content)} rows).")
