"""Parser / sourcetype commands — props.conf and transforms.conf via confs API."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


@click.group("parsers")
def parsers_group() -> None:
    """Manage source types and field extractions."""


@parsers_group.command("sourcetypes")
@click.pass_context
def sourcetypes(ctx: click.Context) -> None:
    """List source types from props.conf."""
    client = get_client(ctx)
    conf = client.service.confs["props"]
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "category": s.content.get("category", ""),
            "description": s.content.get("description", ""),
            "TRANSFORMS": s.content.get("TRANSFORMS", ""),
        }
        for s in conf.list()
    ]
    output.render(ctx, rows)


@parsers_group.command("get")
@click.argument("sourcetype")
@click.pass_context
def get_sourcetype(ctx: click.Context, sourcetype: str) -> None:
    """Show full props.conf settings for a sourcetype."""
    client = get_client(ctx)
    conf = client.service.confs["props"]
    try:
        stanza = conf[sourcetype]
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.")
        ctx.exit(1)
        return
    row: dict[str, Any] = {"name": stanza.name, **dict(stanza.content)}
    output.render(ctx, row)


@parsers_group.command("extractions")
@click.option("--sourcetype", default=None, help="Filter by name substring.")
@click.pass_context
def extractions(ctx: click.Context, sourcetype: str | None) -> None:
    """List field extractions from transforms.conf."""
    client = get_client(ctx)
    conf = client.service.confs["transforms"]
    rows: list[dict[str, Any]] = []
    for stanza in conf.list():
        if sourcetype and sourcetype not in stanza.name:
            continue
        rows.append(
            {
                "name": stanza.name,
                "REGEX": stanza.content.get("REGEX", ""),
                "FORMAT": stanza.content.get("FORMAT", ""),
                "DEST_KEY": stanza.content.get("DEST_KEY", ""),
            }
        )
    output.render(ctx, rows)


@parsers_group.command("create")
@click.option("--sourcetype", required=True, help="Sourcetype name.")
@click.option("--category", default=None, help="Category value.")
@click.option(
    "--transforms",
    "transforms_val",
    default=None,
    help="TRANSFORMS value.",
)
@click.pass_context
def create_sourcetype(
    ctx: click.Context,
    sourcetype: str,
    category: str | None,
    transforms_val: str | None,
) -> None:
    """Create a props.conf stanza."""
    kwargs: dict[str, str] = {}
    if category:
        kwargs["category"] = category
    if transforms_val:
        kwargs["TRANSFORMS"] = transforms_val

    details = f"  sourcetype: {sourcetype}"
    for k, v in kwargs.items():
        details += f"\n  {k}: {v}"

    if not guard.check(ctx, f"Create sourcetype '{sourcetype}'", details=details):
        return

    client = get_client(ctx)
    conf = client.service.confs["props"]
    conf.create(sourcetype, **kwargs)
    output.info(f"Created sourcetype '{sourcetype}'.")


@parsers_group.command("update")
@click.argument("sourcetype")
@click.option("--category", default=None, help="Category value.")
@click.option(
    "--transforms",
    "transforms_val",
    default=None,
    help="TRANSFORMS value.",
)
@click.pass_context
def update_sourcetype(
    ctx: click.Context,
    sourcetype: str,
    category: str | None,
    transforms_val: str | None,
) -> None:
    """Update a props.conf stanza."""
    kwargs: dict[str, str] = {}
    if category:
        kwargs["category"] = category
    if transforms_val:
        kwargs["TRANSFORMS"] = transforms_val

    if not kwargs:
        output.error("Nothing to update — pass at least one option.")
        ctx.exit(1)
        return

    details = f"  sourcetype: {sourcetype}"
    for k, v in kwargs.items():
        details += f"\n  {k}: {v}"

    if not guard.check(ctx, f"Update sourcetype '{sourcetype}'", details=details):
        return

    client = get_client(ctx)
    conf = client.service.confs["props"]
    try:
        stanza = conf[sourcetype]
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.")
        ctx.exit(1)
        return
    stanza.update(**kwargs).refresh()
    output.info(f"Updated sourcetype '{sourcetype}'.")


@parsers_group.command("delete")
@click.argument("sourcetype")
@click.pass_context
def delete_sourcetype(ctx: click.Context, sourcetype: str) -> None:
    """Delete a props.conf stanza."""
    if not guard.check(
        ctx,
        f"Delete sourcetype '{sourcetype}'",
        details=f"  sourcetype: {sourcetype}",
    ):
        return

    client = get_client(ctx)
    conf = client.service.confs["props"]
    try:
        stanza = conf[sourcetype]
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.")
        ctx.exit(1)
        return
    stanza.delete()
    output.info(f"Deleted sourcetype '{sourcetype}'.")
