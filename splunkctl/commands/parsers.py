"""Parser / sourcetype commands — props.conf and transforms.conf via confs API."""

import json
from typing import Any
from urllib.parse import quote

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import conf_ops
from splunkctl.commands.common import (
    fetch_page,
    filter_by_name,
    list_options,
    page_slice,
    parse_set,
)
from splunkctl.commands.parsers_io import export_parsers, import_parsers


@click.group("parsers")
def parsers_group() -> None:
    """Manage source types and field extractions."""


parsers_group.add_command(export_parsers)
parsers_group.add_command(import_parsers)


@parsers_group.command("set")
@guard.guarded
@click.argument("stanza")
@click.argument("pairs", nargs=-1, required=True)
@click.option(
    "--conf",
    "conf_name",
    type=click.Choice(["props", "transforms"]),
    default="props",
    help="Target conf file (default props).",
)
@click.option(
    "--sharing",
    type=click.Choice(["user", "app", "global"]),
    default=None,
    help="Promote stanza sharing (new stanzas default to app).",
)
@click.option(
    "--create/--no-create",
    "create_missing",
    default=True,
    help="Create the stanza when missing (default: create).",
)
@click.pass_context
def set_keys(
    ctx: click.Context,
    stanza: str,
    pairs: tuple[str, ...],
    conf_name: str,
    sharing: str | None,
    *,
    create_missing: bool,
) -> None:
    """Set one or more KEY=VALUE parsing keys on a conf stanza.

    Examples: TIME_FORMAT, LINE_BREAKER, SHOULD_LINEMERGE, EXTRACT-*,
    REPORT-*, REGEX/FORMAT (with --conf transforms). New stanzas are
    app-shared by default — user-private parsing stanzas do not apply
    at index time.
    """
    kv = parse_set(pairs)
    details = f"  conf: {conf_name}\n  stanza: {stanza}"
    for k, v in kv.items():
        details += f"\n  {k} = {v}"
    if sharing:
        details += f"\n  sharing -> {sharing}"

    if not guard.check(ctx, f"Set {len(kv)} key(s) on '{stanza}'", details=details):
        return

    client = get_client(ctx)
    try:
        _target, created = conf_ops.set_keys(
            client,
            conf_name,
            stanza,
            kv,
            sharing=sharing,
            create_missing=create_missing,
        )
    except KeyError:
        output.error(
            f"Stanza '{stanza}' not found in {conf_name}.conf.", kind="not_found"
        )
        ctx.exit(1)
        return

    verb = "Created" if created else "Updated"
    output.info(f"{verb} {conf_name} stanza '{stanza}' ({len(kv)} key(s)).")


@parsers_group.command("unset")
@guard.guarded
@click.argument("stanza")
@click.argument("keys", nargs=-1, required=True)
@click.option(
    "--conf",
    "conf_name",
    type=click.Choice(["props", "transforms"]),
    default="props",
    help="Target conf file (default props).",
)
@click.pass_context
def unset_keys(
    ctx: click.Context,
    stanza: str,
    keys: tuple[str, ...],
    conf_name: str,
) -> None:
    """Clear parsing keys on a conf stanza.

    The REST API cannot remove a conf key, so values are set to the
    empty string (which disables most parsing keys).
    """
    details = f"  conf: {conf_name}\n  stanza: {stanza}\n  clear: {', '.join(keys)}"
    if not guard.check(ctx, f"Clear {len(keys)} key(s) on '{stanza}'", details=details):
        return

    client = get_client(ctx)
    try:
        conf_ops.unset_keys(client, conf_name, stanza, keys)
    except KeyError:
        output.error(
            f"Stanza '{stanza}' not found in {conf_name}.conf.", kind="not_found"
        )
        ctx.exit(1)
        return
    output.info(
        f"Cleared {len(keys)} key(s) on '{stanza}' "
        "(REST cannot remove conf keys; values set to empty)."
    )


@parsers_group.command("sourcetypes")
@list_options
@click.pass_context
def sourcetypes(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List source types from props.conf."""
    client = get_client(ctx)
    conf = client.service.confs["props"]
    stanzas = fetch_page(conf.list, limit=limit, offset=offset, name_filter=name_filter)
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "category": s.content.get("category", ""),
            "description": s.content.get("description", ""),
            "TRANSFORMS": s.content.get("TRANSFORMS", ""),
        }
        for s in stanzas
    ]
    output.render(ctx, rows, empty="No sourcetypes found.")


@parsers_group.command("get")
@click.argument("sourcetype")
@click.option(
    "--conf",
    "conf_name",
    type=click.Choice(["props", "transforms"]),
    default="props",
    help="Conf file to read (default props).",
)
@click.option(
    "--app",
    default="search",
    help="App namespace for --explicit (default search).",
)
@click.option(
    "--explicit",
    is_flag=True,
    help="Show only explicitly set stanza keys, not the merged view.",
)
@click.pass_context
def get_sourcetype(
    ctx: click.Context,
    sourcetype: str,
    conf_name: str,
    app: str,
    *,
    explicit: bool,
) -> None:
    """Show conf settings for a sourcetype (merged, or --explicit only)."""
    client = get_client(ctx)
    if explicit:
        path = (
            f"/servicesNS/nobody/{quote(app, safe='')}"
            f"/configs/conf-{conf_name}/{quote(sourcetype, safe='')}"
        )
        try:
            resp = client.service.get(path, output_mode="json")
        except Exception:
            output.error(f"Sourcetype '{sourcetype}' not found.", kind="not_found")
            ctx.exit(1)
            return
        body = json.loads(resp.body.read())
        content: dict[str, Any] = body["entry"][0]["content"]
        row = {"name": sourcetype}
        row.update(
            {
                k: v
                for k, v in content.items()
                if not k.startswith("eai:") and k != "disabled"
            }
        )
        output.render(ctx, row)
        return

    try:
        stanza = conf_ops.get_stanza(client, conf_name, sourcetype)
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.", kind="not_found")
        ctx.exit(1)
        return
    row = {"name": stanza.name, **dict(stanza.content)}
    output.render(ctx, row)


@parsers_group.command("reload")
@guard.guarded
@click.option(
    "--conf",
    "conf_name",
    type=click.Choice(["props", "transforms", "all"]),
    default="all",
    help="Which conf to reload (default all).",
)
@click.pass_context
def reload_confs(ctx: click.Context, conf_name: str) -> None:
    """Reload props/transforms so parser changes take effect."""
    targets = ["props", "transforms"] if conf_name == "all" else [conf_name]
    if not guard.check(ctx, f"Reload conf: {', '.join(targets)}"):
        return
    client = get_client(ctx)
    for t in targets:
        conf_ops.reload_conf(client, t)
    output.info(f"Reloaded: {', '.join(targets)}.")


@parsers_group.command("extractions")
@click.option("--sourcetype", default=None, help="Filter by name substring.")
@list_options
@click.pass_context
def extractions(
    ctx: click.Context,
    *,
    sourcetype: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List field extractions from transforms.conf."""
    client = get_client(ctx)
    conf = client.service.confs["transforms"]
    if sourcetype is None:
        stanzas = fetch_page(
            conf.list, limit=limit, offset=offset, name_filter=name_filter
        )
    else:
        # --sourcetype keeps its client-side substring semantics; paging
        # then applies to the filtered set.
        stanzas = [s for s in conf.list() if sourcetype in s.name]
        stanzas = filter_by_name(stanzas, name_filter)
        stanzas = page_slice(stanzas, limit=limit, offset=offset)
    rows: list[dict[str, Any]] = [
        {
            "name": stanza.name,
            "REGEX": stanza.content.get("REGEX", ""),
            "FORMAT": stanza.content.get("FORMAT", ""),
            "DEST_KEY": stanza.content.get("DEST_KEY", ""),
        }
        for stanza in stanzas
    ]
    output.render(ctx, rows)


@parsers_group.command("create")
@guard.guarded
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
@guard.guarded
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
    try:
        stanza = conf_ops.get_stanza(client, "props", sourcetype)
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.", kind="not_found")
        ctx.exit(1)
        return
    stanza.update(**kwargs).refresh()
    output.info(f"Updated sourcetype '{sourcetype}'.")


@parsers_group.command("delete")
@guard.guarded
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
    try:
        stanza = conf_ops.get_stanza(client, "props", sourcetype)
    except KeyError:
        output.error(f"Sourcetype '{sourcetype}' not found.", kind="not_found")
        ctx.exit(1)
        return
    stanza.delete()
    output.info(f"Deleted sourcetype '{sourcetype}'.")
