"""SOAR vault — list, get, upload, download, delete."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import soar_check
from splunkctl.soar.client import SOARError

_WARN_SIZE_BYTES: int = 30 * 1024 * 1024  # 30 MB


def _file_size_bytes(path: Path) -> int:
    """Return file size in bytes (extracted for test patching)."""
    return path.stat().st_size


@click.group("vault")
def vault_group() -> None:
    """Vault (file attachment) operations — list, get, upload, download, delete."""


@vault_group.command("list")
@click.option(
    "--container",
    default=None,
    help="Filter by container ID.",
)
@click.pass_context
def list_cmd(ctx: click.Context, *, container: str | None) -> None:
    """List vault items, optionally filtered by container."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {}
    if container is not None:
        params["_filter_container"] = container

    try:
        result = client.get("container_attachment", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No vault items found.")


@vault_group.command("get")
@click.argument("vault_id")
@click.pass_context
def get_cmd(ctx: click.Context, *, vault_id: str) -> None:
    """Get vault document metadata by vault_id (SHA1 hash)."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {"_filter_hash": f'"{vault_id}"'}

    try:
        result = client.get("vault_document", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    if not data:
        output.error(
            f"No vault item with vault_id '{vault_id}'.",
            kind="not_found",
        )
        ctx.exit(1)
        return

    output.render(ctx, data)


@vault_group.command("upload")
@click.option(
    "--container",
    required=True,
    type=int,
    help="Container ID to attach the file to.",
)
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def upload_cmd(ctx: click.Context, *, container: int, file_path: str) -> None:
    """Upload a file to the vault (base64-encoded via container_attachment)."""
    path = Path(file_path)
    size = _file_size_bytes(path)

    if size > _WARN_SIZE_BYTES:
        mb = size / (1024 * 1024)
        output.warning(
            f"File is {mb:.1f} MB — SOAR's nginx proxy caps uploads at "
            f"~32 MB. Upload may be rejected."
        )

    details = f"  file: {path.name} ({size:,} bytes)\n  container: {container}"
    if not soar_check(ctx, f"Upload '{path.name}' to vault", details=details):
        return

    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode()

    body: dict[str, Any] = {
        "container_id": container,
        "file_name": path.name,
        "file_content": encoded,
    }

    try:
        result = client_post(ctx, body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result)


def client_post(ctx: click.Context, body: dict[str, Any]) -> dict[str, Any]:
    """Post to container_attachment (factored for testability)."""
    client = get_soar_client(ctx)
    result: Any = client.post("container_attachment", body=body)
    if not isinstance(result, dict):
        return {}
    return result


@vault_group.command("download")
@click.argument("vault_id")
@click.option(
    "--out",
    default=None,
    type=click.Path(),
    help="Write to this file instead of stdout.",
)
@click.pass_context
def download_cmd(ctx: click.Context, *, vault_id: str, out: str | None) -> None:
    """Download a vault file by vault_id (SHA1 hash)."""
    client = get_soar_client(ctx)

    try:
        raw = client.get_bytes("download_attachment", params={"vault_id": vault_id})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if out:
        Path(out).write_bytes(raw)
        output.info(f"Written {len(raw):,} bytes to {out}")
    else:
        sys.stdout.buffer.write(raw)


@vault_group.command("delete")
@click.argument("attachment_id", type=int)
@click.pass_context
def delete_cmd(ctx: click.Context, *, attachment_id: int) -> None:
    """Delete a vault attachment by its container_attachment ID.

    SOAR's vault_document DELETE endpoint returns 405; use the
    container_attachment ID (from ``vault list`` or ``vault get``).
    """
    details = f"  container_attachment id: {attachment_id}"
    if not soar_check(ctx, f"Delete vault attachment {attachment_id}", details=details):
        return

    client = get_soar_client(ctx)

    try:
        result = client.delete(f"container_attachment/{attachment_id}")
    except SOARError as exc:
        if exc.http_status == 405:
            output.error(
                "DELETE returned 405. SOAR's vault_document endpoint does "
                "not support DELETE — use the container_attachment ID "
                "(shown by 'vault list' or 'vault get').",
                kind="http",
                http_status=405,
            )
        else:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.info("Deleted.")
