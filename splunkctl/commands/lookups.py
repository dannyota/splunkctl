"""Lookup table commands — raw REST (SDK gap)."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_READ_BASE = "/servicesNS/-/{app}/data/lookup-table-files"
_WRITE_BASE = "/servicesNS/nobody/{app}/data/lookup-table-files"


def _read_path(app: str, name: str | None = None) -> str:
    base = _READ_BASE.format(app=quote(app, safe=""))
    return f"{base}/{quote(name, safe='')}" if name else base


def _write_path(app: str, name: str | None = None) -> str:
    base = _WRITE_BASE.format(app=quote(app, safe=""))
    return f"{base}/{quote(name, safe='')}" if name else base


def _parse_entries(body: bytes) -> list[dict[str, Any]]:
    """Extract flat rows from Splunk REST JSON response."""
    data: dict[str, Any] = json.loads(body)
    return [
        {
            "name": entry.get("name", ""),
            "app": entry.get("acl", {}).get("app", ""),
            "owner": entry.get("acl", {}).get("owner", ""),
            "disabled": entry.get("content", {}).get("disabled", ""),
            "eai:type": entry.get("content", {}).get("eai:type", ""),
            "updated": entry.get("updated", ""),
        }
        for entry in data.get("entry", [])
    ]


def _parse_entry(body: bytes) -> dict[str, Any]:
    """Extract a single entry from Splunk REST JSON response."""
    data: dict[str, Any] = json.loads(body)
    entries: list[dict[str, Any]] = data.get("entry", [])
    if not entries:
        return {}
    entry = entries[0]
    content: dict[str, Any] = entry.get("content", {})
    return {
        "name": entry.get("name", ""),
        "app": entry.get("acl", {}).get("app", ""),
        "owner": entry.get("acl", {}).get("owner", ""),
        "disabled": content.get("disabled", ""),
        "eai:type": content.get("eai:type", ""),
        "eai:data": content.get("eai:data", ""),
        "updated": entry.get("updated", ""),
    }


@click.group("lookups")
def lookups_group() -> None:
    """Manage lookup table files."""


@lookups_group.command("list")
@click.option("--app", default="-", help="Splunk app context (default: all).")
@click.pass_context
def list_lookups(ctx: click.Context, *, app: str) -> None:
    """List lookup table files."""
    client = get_client(ctx)
    svc = client.service
    resp = svc.get(_read_path(app), output_mode="json")
    body: bytes = resp.body.read()
    rows = _parse_entries(body)
    if not rows:
        output.info("No lookup tables found.")
        return
    output.render(ctx, rows)


@lookups_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context (default: all).")
@click.pass_context
def get_lookup(ctx: click.Context, name: str, *, app: str) -> None:
    """Get metadata for a lookup file."""
    client = get_client(ctx)
    svc = client.service
    try:
        resp = svc.get(_read_path(app, name), output_mode="json")
    except Exception as exc:
        output.error(f"Lookup '{name}' not found: {exc}")
        ctx.exit(1)
        return
    body: bytes = resp.body.read()
    row = _parse_entry(body)
    if not row:
        output.error(f"Lookup '{name}' not found.")
        ctx.exit(1)
        return
    output.render(ctx, row)


@lookups_group.command("upload")
@click.argument("name")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True),
    help="CSV file to upload.",
)
@click.option("--app", default="search", help="Target app (default: search).")
@click.pass_context
def upload_lookup(ctx: click.Context, name: str, file_path: str, *, app: str) -> None:
    """Upload a CSV file as a new lookup table."""
    path = Path(file_path)
    details = f"Upload '{path.name}' as lookup '{name}' in app '{app}'"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service
    csv_data = path.read_text(encoding="utf-8")
    try:
        svc.post(
            _write_path(app),
            name=name,
            **{"eai:data": csv_data},
        )
    except Exception as exc:
        output.error(f"Upload failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Uploaded lookup '{name}' to app '{app}'.")


@lookups_group.command("download")
@click.argument("name")
@click.option("--app", default="search", help="Splunk app context.")
@click.option("--out", type=click.Path(), default=None, help="Write CSV to file.")
@click.pass_context
def download_lookup(
    ctx: click.Context, name: str, *, app: str, out: str | None
) -> None:
    """Download a lookup table as CSV."""
    client = get_client(ctx)
    svc = client.service
    try:
        stream = svc.jobs.oneshot(f"| inputlookup {name}", output_mode="csv", app=app)
        csv_content = stream.read().decode("utf-8")
    except Exception as exc:
        output.error(f"Download failed: {exc}")
        ctx.exit(1)
        return

    if out:
        Path(out).write_text(csv_content, encoding="utf-8")
        output.info(f"Written to {out}")
    else:
        click.echo(csv_content, nl=False)


@lookups_group.command("update")
@click.argument("name")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True),
    help="CSV file to upload.",
)
@click.option("--app", default="search", help="Target app (default: search).")
@click.pass_context
def update_lookup(ctx: click.Context, name: str, file_path: str, *, app: str) -> None:
    """Overwrite an existing lookup table with new CSV data."""
    path = Path(file_path)
    details = f"Overwrite lookup '{name}' in app '{app}' with '{path.name}'"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service
    csv_data = path.read_text(encoding="utf-8")
    try:
        svc.post(
            _write_path(app, name),
            **{"eai:data": csv_data},
        )
    except Exception as exc:
        output.error(f"Update failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Updated lookup '{name}' in app '{app}'.")


@lookups_group.command("delete")
@click.argument("name")
@click.option("--app", default="search", help="Target app (default: search).")
@click.pass_context
def delete_lookup(ctx: click.Context, name: str, *, app: str) -> None:
    """Delete a lookup table file."""
    details = f"Delete lookup '{name}' from app '{app}'"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service
    try:
        svc.delete(_write_path(app, name))
    except Exception as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Deleted lookup '{name}' from app '{app}'.")
