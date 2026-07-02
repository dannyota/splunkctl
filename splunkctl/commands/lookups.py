"""Lookup table commands via SDK."""

from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


@click.group("lookups")
def lookups_group() -> None:
    """Manage lookup table files."""


@lookups_group.command("list")
@click.option("--app", default="-", help="Splunk app context (default: all).")
@click.pass_context
def list_lookups(ctx: click.Context, *, app: str) -> None:
    """List lookup table files."""
    client = get_client(ctx)
    items = client.service.lookup_table_files.list(app=app, owner="-")
    rows: list[dict[str, Any]] = [
        {
            "name": lk.name,
            "app": lk.access.app,
            "owner": lk.access.owner,
            "disabled": lk.content.get("disabled", ""),
            "eai:type": lk.content.get("eai:type", ""),
        }
        for lk in items
    ]
    output.render(ctx, rows, empty="No lookup tables found.")


@lookups_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context (default: all).")
@click.pass_context
def get_lookup(ctx: click.Context, name: str, *, app: str) -> None:
    """Get metadata for a lookup file."""
    client = get_client(ctx)
    try:
        matches = client.service.lookup_table_files.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        lk = matches[0]
    except (KeyError, Exception) as exc:
        output.error(f"Lookup '{name}' not found: {exc}")
        ctx.exit(1)
        return
    row: dict[str, Any] = {
        "name": lk.name,
        "app": lk.access.app,
        "owner": lk.access.owner,
        "disabled": lk.content.get("disabled", ""),
        "eai:type": lk.content.get("eai:type", ""),
        "eai:data": lk.content.get("eai:data", ""),
    }
    output.render(ctx, row)


@lookups_group.command("upload")
@guard.guarded
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
    try:
        client.upload_lookup(name, path, app=app)
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
    try:
        matches = client.service.lookup_table_files.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
    except Exception as exc:
        output.error(f"Download failed: {exc}")
        ctx.exit(1)
        return
    if not matches:
        output.error(f"Lookup '{name}' not found in app '{app}'.")
        ctx.exit(1)
        return
    try:
        stream = client.service.jobs.oneshot(
            f"| inputlookup {name}",
            output_mode="csv",
            app=app,
        )
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
@guard.guarded
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
    try:
        client.upload_lookup(name, path, app=app, update=True)
    except Exception as exc:
        output.error(f"Update failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Updated lookup '{name}' in app '{app}'.")


@lookups_group.command("delete")
@guard.guarded
@click.argument("name")
@click.option("--app", default="search", help="Target app (default: search).")
@click.pass_context
def delete_lookup(ctx: click.Context, name: str, *, app: str) -> None:
    """Delete a lookup table file."""
    details = f"Delete lookup '{name}' from app '{app}'"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    try:
        matches = client.service.lookup_table_files.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        matches[0].delete()
    except (KeyError, Exception) as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Deleted lookup '{name}' from app '{app}'.")
