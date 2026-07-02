"""Data input commands — list, create, update, delete, enable, disable."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import filter_by_name, list_options, page_slice

VALID_KINDS = ("monitor", "tcp", "udp", "script", "http")


def _input_row(inp: Any) -> dict[str, Any]:
    content: dict[str, Any] = dict(inp.content)
    return {
        "name": inp.name,
        "kind": inp.kind,
        "disabled": content.get("disabled", ""),
        "index": content.get("index", ""),
        "sourcetype": content.get("sourcetype", ""),
    }


def _find_input(service: Any, name: str) -> Any:
    for inp in service.inputs.list():
        if inp.name == name:
            return inp
    return None


@click.group("inputs")
def inputs_group() -> None:
    """Manage data inputs."""


@inputs_group.command("list")
@click.option(
    "--kind",
    type=click.Choice(VALID_KINDS),
    default=None,
    help="Filter by input kind.",
)
@list_options
@click.pass_context
def list_inputs(
    ctx: click.Context,
    *,
    kind: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List data inputs.

    --filter/--limit/--offset apply client-side, after the --kind filter
    (the SDK inputs collection is a union across input kinds). Note: the union
    collection pages each kind with a 30-per-kind default limit, so environments
    with >30 inputs of a single kind may return incomplete results. To verify
    completeness for a specific kind, use: splunkctl search oneshot
    '| rest /services/data/inputs/<kind>' (e.g., /services/data/inputs/monitor).
    """
    client = get_client(ctx)
    rows = [_input_row(i) for i in client.service.inputs.list()]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    rows = filter_by_name(rows, name_filter, name_of=lambda r: str(r["name"]))
    rows = page_slice(rows, limit=limit, offset=offset)
    output.render(ctx, rows)


@inputs_group.command()
@click.argument("name")
@click.pass_context
def get(ctx: click.Context, *, name: str) -> None:
    """Show details for a specific input."""
    client = get_client(ctx)
    inp = _find_input(client.service, name)
    if inp is None:
        output.error(f"Input not found: {name}")
        ctx.exit(1)
        return
    row: dict[str, Any] = {"name": inp.name, "kind": inp.kind}
    row.update(dict(inp.content))
    output.render(ctx, row)


@inputs_group.command()
@guard.guarded
@click.option("--name", required=True, help="Input name/path.")
@click.option(
    "--kind",
    required=True,
    type=click.Choice(VALID_KINDS),
    help="Input kind.",
)
@click.option("--index", default=None, help="Target index.")
@click.option("--sourcetype", default=None, help="Source type.")
@click.option("--disabled", is_flag=True, default=False, help="Create disabled.")
@click.pass_context
def create(
    ctx: click.Context,
    *,
    name: str,
    kind: str,
    index: str | None,
    sourcetype: str | None,
    disabled: bool,
) -> None:
    """Create a new data input."""
    kwargs: dict[str, Any] = {}
    if index:
        kwargs["index"] = index
    if sourcetype:
        kwargs["sourcetype"] = sourcetype
    if disabled:
        kwargs["disabled"] = True

    details = f"kind={kind}"
    if kwargs:
        details += ", " + ", ".join(f"{k}={v}" for k, v in kwargs.items())

    if not guard.check(ctx, f"Create input '{name}'", details=details):
        return

    client = get_client(ctx)
    client.service.inputs.create(name, kind, **kwargs)
    output.info(f"Created input: {name} ({kind})")


@inputs_group.command()
@guard.guarded
@click.argument("name")
@click.option("--index", default=None, help="Target index.")
@click.option("--sourcetype", default=None, help="Source type.")
@click.option("--enabled/--disabled", default=None, help="Enable or disable.")
@click.pass_context
def update(
    ctx: click.Context,
    *,
    name: str,
    index: str | None,
    sourcetype: str | None,
    enabled: bool | None,
) -> None:
    """Update an existing data input."""
    kwargs: dict[str, Any] = {}
    if index is not None:
        kwargs["index"] = index
    if sourcetype is not None:
        kwargs["sourcetype"] = sourcetype
    if enabled is not None:
        kwargs["disabled"] = not enabled

    if not kwargs:
        output.error("No update options provided.")
        ctx.exit(1)
        return

    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    if not guard.check(ctx, f"Update input '{name}'", details=details):
        return

    client = get_client(ctx)
    inp = _find_input(client.service, name)
    if inp is None:
        output.error(f"Input not found: {name}")
        ctx.exit(1)
        return
    inp.update(**kwargs).refresh()
    output.info(f"Updated input: {name}")


@inputs_group.command()
@guard.guarded
@click.argument("name")
@click.pass_context
def delete(ctx: click.Context, *, name: str) -> None:
    """Delete a data input."""
    if not guard.check(ctx, f"Delete input '{name}'"):
        return

    client = get_client(ctx)
    inp = _find_input(client.service, name)
    if inp is None:
        output.error(f"Input not found: {name}")
        ctx.exit(1)
        return
    inp.delete()
    output.info(f"Deleted input: {name}")


@inputs_group.command()
@guard.guarded
@click.argument("name")
@click.pass_context
def enable(ctx: click.Context, *, name: str) -> None:
    """Enable a disabled input."""
    if not guard.check(ctx, f"Enable input '{name}'"):
        return

    client = get_client(ctx)
    inp = _find_input(client.service, name)
    if inp is None:
        output.error(f"Input not found: {name}")
        ctx.exit(1)
        return
    inp.enable()
    output.info(f"Enabled input: {name}")


@inputs_group.command()
@guard.guarded
@click.argument("name")
@click.pass_context
def disable(ctx: click.Context, *, name: str) -> None:
    """Disable an input."""
    if not guard.check(ctx, f"Disable input '{name}'"):
        return

    client = get_client(ctx)
    inp = _find_input(client.service, name)
    if inp is None:
        output.error(f"Input not found: {name}")
        ctx.exit(1)
        return
    inp.disable()
    output.info(f"Disabled input: {name}")
