"""Index management — list, get, create, update, delete, clean, reload."""

from typing import Any

import click
from splunklib.client import OperationError

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import fetch_page, list_options

_LIST_FIELDS = (
    "datatype",
    "totalEventCount",
    "currentDBSizeMB",
    "maxTotalDataSizeMB",
    "frozenTimePeriodInSecs",
    "disabled",
)

_DETAIL_FIELDS = (
    "datatype",
    "totalEventCount",
    "currentDBSizeMB",
    "maxTotalDataSizeMB",
    "maxDataSize",
    "homePath_expanded",
    "coldPath_expanded",
    "frozenTimePeriodInSecs",
    "maxHotBuckets",
    "maxWarmDBCount",
    "minTime",
    "maxTime",
    "repFactor",
    "disabled",
    "isInternal",
)


def _index_row(idx: Any, fields: tuple[str, ...] = _LIST_FIELDS) -> dict[str, Any]:
    c: dict[str, Any] = idx.content
    row: dict[str, Any] = {"name": idx.name}
    row.update({f: c.get(f, "") for f in fields})
    return row


@click.group("indexes")
def indexes_group() -> None:
    """Manage Splunk indexes."""


@indexes_group.command("list")
@list_options
@click.pass_context
def list_indexes(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List all indexes."""
    client = get_client(ctx)
    items = fetch_page(
        client.service.indexes.list,
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows = [_index_row(idx) for idx in items]
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
    output.render(ctx, _index_row(idx, _DETAIL_FIELDS))


@indexes_group.command("create")
@guard.guarded
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
        kwargs["maxTotalDataSizeMB"] = max_size
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
@guard.guarded
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
        kwargs["maxTotalDataSizeMB"] = max_size
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
@guard.guarded
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
@guard.guarded
@click.argument("name")
@click.option(
    "--clean-timeout",
    type=int,
    default=60,
    help="Seconds to wait for the index to empty (default 60).",
)
@click.pass_context
def clean_index(ctx: click.Context, name: str, clean_timeout: int) -> None:
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
    try:
        idx.clean(timeout=clean_timeout)
    except OperationError as exc:
        idx.refresh()
        disabled = str(idx.content.get("disabled", "0")) == "1"
        state = "disabled" if disabled else "enabled"
        remaining = idx.content.get("totalEventCount", "?")
        output.error(
            f"Clean did not finish: {exc} "
            f"(index is {state}, {remaining} events remain). "
            f"Retry with a larger --clean-timeout."
        )
        ctx.exit(1)
        return
    output.info(f"Index '{name}' cleaned.")


@indexes_group.command("reload")
@guard.guarded
@click.pass_context
def reload_indexes(ctx: click.Context) -> None:
    """Reload all index configurations."""
    if not guard.check(ctx, "Reload all index configurations"):
        return

    client = get_client(ctx)
    client.service.post("/services/data/indexes/_reload")
    output.info("Index configurations reloaded.")
