"""Lookup table commands via SDK, plus transforms.conf/props.conf wiring.

Table-file CRUD (list/get/upload/update/download/delete) goes straight
through the SDK's ``LookupTableFile``/``LookupTableFiles`` entity classes.
`define`/`auto` wire a table (or a KV store collection) into a usable
search-time lookup — a transforms.conf *definition* stanza and a
props.conf ``LOOKUP-*`` *automatic lookup* — over the shared ``conf_ops``
core (the same one ``conf``/``parsers``/``macros`` use), never hand-rolled
SDK conf access. Value-string/kv construction itself lives in
``lookups_wiring`` so it has a direct unit-test surface of its own.
"""

from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import conf_ops, lookups_wiring
from splunkctl.commands.common import (
    app_scope,
    fetch_page,
    list_options,
    spl_quote_lookup_name,
)


@click.group("lookups")
def lookups_group() -> None:
    """Manage lookup table files."""


@lookups_group.command("list")
@click.option("--app", default="-", help="Splunk app context (default: all).")
@list_options
@click.pass_context
def list_lookups(
    ctx: click.Context,
    *,
    app: str,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List lookup table files."""
    client = get_client(ctx)
    items = fetch_page(
        lambda **pg: client.service.lookup_table_files.list(app=app, owner="-", **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
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
    except KeyError:
        output.error(f"Lookup '{name}' not found.", kind="not_found")
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
        output.error(f"Lookup '{name}' not found in app '{app}'.", kind="not_found")
        ctx.exit(1)
        return
    try:
        quoted = spl_quote_lookup_name(name)
        stream = client.service.jobs.oneshot(
            f"| inputlookup {quoted}",
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
    except KeyError:
        output.error(f"Lookup '{name}' not found in app '{app}'.", kind="not_found")
        ctx.exit(1)
        return
    output.info(f"Deleted lookup '{name}' from app '{app}'.")


# --------------------------------------------------------------------------
# define / auto — transforms.conf definitions and props.conf LOOKUP-* wiring
# --------------------------------------------------------------------------


def _warn_if_file_missing(client: Any, file_name: str, app: str | None) -> None:
    """Best-effort, non-blocking check that ``--file`` names a real lookup.

    Never raises and never blocks the mutation — this is a heads-up for a
    likely typo, not a hard requirement (transforms.conf itself doesn't
    validate the file exists at write time either, and the file may be
    uploaded moments after this runs in a scripted define+upload flow).
    """
    try:
        matches = client.service.lookup_table_files.list(
            search=f"name={file_name}", count=1, **app_scope(app)
        )
    except Exception:
        return
    if not matches:
        where = f" in app '{app}'" if app else ""
        output.warning(
            f"Lookup table file '{file_name}' not found{where} — "
            "'lookups upload' it first, or double-check the filename."
        )


@lookups_group.command("define")
@guard.guarded
@click.argument("defname")
@click.option(
    "--app",
    default=None,
    help="App to scope the definition to (default: current namespace).",
)
@click.option(
    "--file",
    "file_name",
    default=None,
    help="Lookup table CSV/mmdb filename (exactly one of --file/--collection).",
)
@click.option(
    "--collection",
    default=None,
    help="KV store collection name (exactly one of --file/--collection).",
)
@click.option(
    "--max-matches", type=int, default=None, help="Maximum matches per input."
)
@click.option("--min-matches", type=int, default=None, help="Minimum matches required.")
@click.option(
    "--case-sensitive/--no-case-sensitive",
    "case_sensitive",
    default=None,
    help="Case-sensitive field matching (default: Splunk's own default, unset).",
)
@click.option(
    "--default-match",
    default=None,
    help="Value used for the output field(s) when no match is found.",
)
@click.pass_context
def define_lookup(
    ctx: click.Context,
    defname: str,
    *,
    app: str | None,
    file_name: str | None,
    collection: str | None,
    max_matches: int | None,
    min_matches: int | None,
    case_sensitive: bool | None,
    default_match: str | None,
) -> None:
    """Create or update a lookup definition (transforms.conf).

    Binds DEFNAME to a table file (--file) or a KV store collection
    (--collection) — exactly one is required. Use `lookups auto` next to
    wire the definition onto a sourcetype so it enriches events
    automatically, or reference DEFNAME directly with `| lookup`.
    """
    if (file_name is None) == (collection is None):
        raise click.UsageError("exactly one of --file or --collection is required")

    kv = lookups_wiring.build_transforms_kv(
        file=file_name,
        collection=collection,
        max_matches=max_matches,
        min_matches=min_matches,
        case_sensitive=case_sensitive,
        default_match=default_match,
    )

    client = get_client(ctx)
    if file_name is not None:
        _warn_if_file_missing(client, file_name, app)

    try:
        entity = conf_ops.get_stanza(client, "transforms", defname, app=app)
        current: dict[str, Any] = dict(entity.content)
    except KeyError:
        current = {}
    diff = "\n".join(conf_ops.diff_lines(current, kv))
    details = f"  file: transforms.conf\n  stanza: {defname}\n{diff}"

    if not guard.check(
        ctx, f"Set {len(kv)} key(s) on '{defname}' in transforms.conf", details=details
    ):
        return

    _, created = conf_ops.set_keys(client, "transforms", defname, kv, app=app)
    verb = "Created" if created else "Updated"
    output.info(f"{verb} lookup definition '{defname}' ({len(kv)} key(s)).")


@lookups_group.command("auto")
@guard.guarded
@click.argument("defname")
@click.option(
    "--sourcetype", required=True, help="Sourcetype stanza in props.conf to wire onto."
)
@click.option(
    "--input",
    "inputs",
    multiple=True,
    required=True,
    help="Match field: FIELD or FIELD:LOOKUP_FIELD (repeatable, >=1 required). "
    "FIELD is the event's field name; LOOKUP_FIELD, after a ':', is the "
    "lookup table's column name only when it differs.",
)
@click.option(
    "--output",
    "outputs",
    multiple=True,
    required=True,
    help="Output field: FIELD or FIELD:RENAMED (repeatable, >=1 required). "
    "FIELD is the lookup table's column; RENAMED, after a ':', is the "
    "event field name to write it to when it differs.",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    help="OUTPUT (default): always overwrite. --no-overwrite: OUTPUTNEW "
    "(only fill fields not already present on the event).",
)
@click.option(
    "--app",
    default=None,
    help="App to scope the props.conf stanza to (default: current namespace).",
)
@click.option(
    "--name", "autoname", default=None, help="LOOKUP- key suffix (default: DEFNAME)."
)
@click.pass_context
def auto_lookup(
    ctx: click.Context,
    defname: str,
    *,
    sourcetype: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    overwrite: bool,
    app: str | None,
    autoname: str | None,
) -> None:
    """Wire an automatic lookup onto a sourcetype (props.conf LOOKUP-*).

    Requires a lookup definition (see `lookups define`) named DEFNAME to
    already exist. Events of --sourcetype get enriched at search time:
    each --input match field is looked up against DEFNAME, and each
    --output field from a matching row is copied onto the event.
    """
    resolved_name = autoname or defname
    key = f"LOOKUP-{resolved_name}"
    value = lookups_wiring.build_lookup_value(
        defname, inputs, outputs, overwrite=overwrite
    )
    kv = {key: value}

    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, "props", sourcetype, app=app)
        current: dict[str, Any] = dict(entity.content)
    except KeyError:
        current = {}
    diff = "\n".join(conf_ops.diff_lines(current, kv))
    details = f"  file: props.conf\n  stanza: {sourcetype}\n{diff}"

    if not guard.check(
        ctx, f"Set '{key}' on '{sourcetype}' in props.conf", details=details
    ):
        return

    _, created = conf_ops.set_keys(client, "props", sourcetype, kv, app=app)
    verb = "Created" if created else "Updated"
    output.info(f"{verb} '{key}' on props stanza '{sourcetype}'.")


_LOOKUP_DEF_KEYS = ("filename", "external_type", "collection")


@lookups_group.command("definitions")
@click.option(
    "--app",
    default=None,
    help="Only definitions in this app (default: current namespace, which "
    "may miss app-private stanzas — pass --app to see them all).",
)
@list_options
@click.pass_context
def list_definitions(
    ctx: click.Context,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List transforms.conf lookup-definition stanzas.

    transforms.conf also holds unrelated field-transform stanzas (REGEX/
    FORMAT); only stanzas shaped like a lookup definition (a `filename`
    or `external_type`/`collection` key) are shown here. For the full,
    unfiltered transforms.conf, use `conf list transforms`.
    """
    client = get_client(ctx)
    items = fetch_page(
        lambda **pg: client.service.confs["transforms"].list(**app_scope(app), **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "app": dict(s.access).get("app", ""),
            **{k: s.content[k] for k in _LOOKUP_DEF_KEYS if k in s.content},
        }
        for s in items
        if any(k in s.content for k in _LOOKUP_DEF_KEYS)
    ]
    output.render(ctx, rows, empty="No lookup definitions found.")
