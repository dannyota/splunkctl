"""Index management — list, get, create, update, delete, clean, reload."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_LIST_FIELDS = (
    "name",
    "datatype",
    "totalEventCount",
    "currentDBSizeMB",
    "maxDataSizeMB",
    "frozenTimePeriodInSecs",
    "disabled",
)


def _index_row(idx: Any, fields: tuple[str, ...] = _LIST_FIELDS) -> dict[str, Any]:
    content: dict[str, Any] = dict(idx.content)
    row: dict[str, Any] = {"name": idx.name}
    for f in fields:
        if f != "name":
            row[f] = content.get(f, "")
    return row


@click.group("indexes")
def indexes_group() -> None:
    """Manage Splunk indexes."""


@indexes_group.command("list")
@click.pass_context
def list_indexes(ctx: click.Context) -> None:
    """List all indexes."""
    client = get_client(ctx)
    rows = [_index_row(idx) for idx in client.service.indexes.list()]
    output.render(ctx, rows)


@indexes_group.command("get")
@click.argument("name")
@click.pass_context
def get_index(ctx: click.Context, name: str) -> None:
    """Get full index details."""
    client = get_client(ctx)
    try:
        idx = client.service.indexes[name]
    except KeyError:
        output.error(f"Index '{name}' not found.")
        ctx.exit(1)
        return
    row: dict[str, Any] = {"name": idx.name, **dict(idx.content)}
    output.render(ctx, row)


@indexes_group.command("create")
@click.option("--name", required=True, help="Index name.")
@click.option(
    "--datatype",
    type=click.Choice(["event", "metric"]),
    default=None,
    help="Index datatype.",
)
@click.option("--max-size", type=int, default=None, help="Max data size in MB.")
@click.option(
    "--frozen-period", type=int, default=None, help="Frozen time period in seconds."
)
@click.option("--home-path", default=None, help="Home path for hot/warm buckets.")
@click.option("--cold-path", default=None, help="Cold path for cold buckets.")
@click.pass_context
def create_index(
    ctx: click.Context,
    name: str,
    datatype: str | None,
    max_size: int | None,
    frozen_period: int | None,
    home_path: str | None,
    cold_path: str | None,
) -> None:
    """Create a new index."""
    kwargs: dict[str, Any] = {}
    if datatype is not None:
        kwargs["datatype"] = datatype
    if max_size is not None:
        kwargs["maxDataSizeMB"] = max_size
    if frozen_period is not None:
        kwargs["frozenTimePeriodInSecs"] = frozen_period
    if home_path is not None:
        kwargs["homePath"] = home_path
    if cold_path is not None:
        kwargs["coldPath"] = cold_path

    details = f"  name={name}"
    for k, v in kwargs.items():
        details += f"\n  {k}={v}"

    if not guard.check(ctx, f"Create index '{name}'", details=details):
        return

    client = get_client(ctx)
    client.service.indexes.create(name, **kwargs)
    output.info(f"Index '{name}' created.")


@indexes_group.command("update")
@click.argument("name")
@click.option("--max-size", type=int, default=None, help="Max data size in MB.")
@click.option(
    "--frozen-period", type=int, default=None, help="Frozen time period in seconds."
)
@click.pass_context
def update_index(
    ctx: click.Context,
    name: str,
    max_size: int | None,
    frozen_period: int | None,
) -> None:
    """Update index settings."""
    kwargs: dict[str, Any] = {}
    if max_size is not None:
        kwargs["maxDataSizeMB"] = max_size
    if frozen_period is not None:
        kwargs["frozenTimePeriodInSecs"] = frozen_period

    if not kwargs:
        output.error("No settings to update. Provide --max-size or --frozen-period.")
        ctx.exit(1)
        return

    details = f"  index={name}"
    for k, v in kwargs.items():
        details += f"\n  {k}={v}"

    if not guard.check(ctx, f"Update index '{name}'", details=details):
        return

    client = get_client(ctx)
    try:
        idx = client.service.indexes[name]
    except KeyError:
        output.error(f"Index '{name}' not found.")
        ctx.exit(1)
        return
    idx.update(**kwargs).refresh()
    output.info(f"Index '{name}' updated.")


@indexes_group.command("delete")
@click.argument("name")
@click.pass_context
def delete_index(ctx: click.Context, name: str) -> None:
    """Delete an index."""
    if not guard.check(ctx, f"Delete index '{name}'"):
        return

    client = get_client(ctx)
    try:
        idx = client.service.indexes[name]
    except KeyError:
        output.error(f"Index '{name}' not found.")
        ctx.exit(1)
        return
    idx.delete()
    output.info(f"Index '{name}' deleted.")


@indexes_group.command("clean")
@click.argument("name")
@click.pass_context
def clean_index(ctx: click.Context, name: str) -> None:
    """Remove all events from an index."""
    if not guard.check(ctx, f"Clean index '{name}' (remove all events)"):
        return

    client = get_client(ctx)
    try:
        idx = client.service.indexes[name]
    except KeyError:
        output.error(f"Index '{name}' not found.")
        ctx.exit(1)
        return
    idx.clean(timeout=60)
    output.info(f"Index '{name}' cleaned.")


@indexes_group.command("reload")
@click.pass_context
def reload_indexes(ctx: click.Context) -> None:
    """Reload all index configurations."""
    if not guard.check(ctx, "Reload all index configurations"):
        return

    client = get_client(ctx)
    client.service.post("/services/data/indexes/_reload")
    output.info("Index configurations reloaded.")
