"""SOAR custom functions — list, get, import, export, update, delete."""

from __future__ import annotations

import base64
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import guarded, soar_check
from splunkctl.soar.client import SOARError


def _dir_to_tgz(directory: Path) -> bytes:
    """Pack a directory into an in-memory tgz archive."""
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for child in sorted(directory.iterdir()):
            if child.is_file():
                tar.add(str(child), arcname=child.name)
    buf.seek(0)
    return buf.read()


def _resolve_scm_id(client: Any) -> int | None:
    """Resolve the local SCM repo id via GET /rest/scm."""
    try:
        result = client.get("scm", params={})
    except SOARError:
        return None
    data = result.get("data", []) if isinstance(result, dict) else []
    for repo in data:
        if isinstance(repo, dict) and repo.get("id") is not None:
            return int(repo["id"])
    return None


@click.group("functions")
def functions_group() -> None:
    """Custom function operations — list, get, import, update, delete."""


@functions_group.command("list")
@click.option("--limit", default=None, type=int, help="Max results.")
@click.option("--offset", default=None, type=int, help="Page offset.")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int | None,
) -> None:
    """List custom functions."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {}
    if limit is not None:
        params["page_size"] = limit
    if offset is not None:
        params["page"] = offset

    try:
        result = client.get("custom_function", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No custom functions found.")


@functions_group.command("get")
@click.argument("function_id", type=int)
@click.pass_context
def get_cmd(ctx: click.Context, *, function_id: int) -> None:
    """Get a custom function by ID."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"custom_function/{function_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)


@functions_group.command("import")
@guarded
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def import_cmd(ctx: click.Context, *, path: str) -> None:
    """Import a custom function from a directory or .tgz archive.

    A directory is packed into a tgz automatically. The archive is
    base64-encoded and posted to ``/rest/import_custom_function``.
    """
    src = Path(path)

    if src.is_dir():
        details = f"  source: directory {src.name}/"
    else:
        details = f"  source: {src.name} ({src.stat().st_size:,} bytes)"

    if not soar_check(
        ctx, f"Import custom function from '{src.name}'", details=details
    ):
        return

    if src.is_dir():
        raw = _dir_to_tgz(src)
    else:
        raw = src.read_bytes()

    encoded = base64.b64encode(raw).decode()
    body: dict[str, Any] = {
        "custom_function": encoded,
        "scm": "local",
        "force": True,
    }

    client = get_soar_client(ctx)

    try:
        result = client.post("import_custom_function", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        cf_id = result.get("id", "?")
        output.info(f"Custom function imported: id={cf_id}")
        output.render(ctx, result)
    else:
        output.info("Custom function imported.")


@functions_group.command("export")
@click.argument("function_id", type=int)
@click.option(
    "--out",
    default=None,
    type=click.Path(),
    help="Write tgz to this file instead of stdout.",
)
@click.pass_context
def export_cmd(ctx: click.Context, *, function_id: int, out: str | None) -> None:
    """Export a custom function as a tgz archive."""
    client = get_soar_client(ctx)

    try:
        raw = client.get_bytes(f"custom_function/{function_id}/export", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if out:
        Path(out).write_bytes(raw)
        output.info(f"Written {len(raw):,} bytes to {out}")
    else:
        click.get_binary_stream("stdout").write(raw)


@functions_group.command("update")
@guarded
@click.argument("function_id", type=int)
@click.option(
    "--python",
    "python_file",
    required=True,
    type=click.Path(exists=True),
    help="Python source file to upload.",
)
@click.option(
    "--message",
    required=True,
    help="Commit message (required by SOAR SCM).",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    *,
    function_id: int,
    python_file: str,
    message: str,
) -> None:
    """Update a custom function's Python source.

    Reads the new source from ``--python``, resolves the SCM repo id,
    fetches the existing record, and posts only the changed fields
    (python + commit_message + scm_id).
    """
    py_path = Path(python_file)
    details = (
        f"  function id: {function_id}\n"
        f"  python: {py_path.name} ({py_path.stat().st_size:,} bytes)\n"
        f"  message: {message}"
    )
    if not soar_check(ctx, f"Update custom function {function_id}", details=details):
        return

    client = get_soar_client(ctx)

    # Resolve SCM id.
    scm_id = _resolve_scm_id(client)
    if scm_id is None:
        output.error(
            "No SCM repository found on this SOAR instance. "
            "Custom function update requires at least one SCM repo.",
            kind="error",
        )
        ctx.exit(1)
        return

    # Fetch existing record to merge.
    try:
        existing = client.get(f"custom_function/{function_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_python = py_path.read_text()

    # Preserve fields from the existing record.
    _MERGE_KEYS = (
        "name",
        "module",
        "draft_mode",
        "python_version",
        "outputs_type",
    )
    body: dict[str, Any] = {}
    if isinstance(existing, dict):
        for key in _MERGE_KEYS:
            if key in existing:
                body[key] = existing[key]
        # SOAR 8.x runs Python 3.13; legacy 2.7 records must be
        # upgraded or the server rejects the update.
        if body.get("python_version") in ("2", "2.7"):
            body["python_version"] = "3"
            output.warning(
                "upgrading python_version 2.7 -> 3"
                " (SOAR 8.x rejects editing py2 functions)"
            )

    body["python"] = new_python
    body["commit_message"] = message
    body["scm_id"] = scm_id

    try:
        result = client.post(f"custom_function/{function_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Custom function {function_id} updated.")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


@functions_group.command("delete")
@guarded
@click.argument("function_id", type=int)
@click.pass_context
def delete_cmd(ctx: click.Context, *, function_id: int) -> None:
    """Delete a custom function (requires Basic auth)."""
    details = f"  custom_function id: {function_id}"
    if not soar_check(ctx, f"Delete custom function {function_id}", details=details):
        return

    client = get_soar_client(ctx)

    try:
        client.delete(f"custom_function/{function_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Custom function {function_id} deleted.")
