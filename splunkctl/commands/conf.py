"""Generic conf editor — any Splunk conf file/stanza via the confs API.

The escape hatch for conf files without a dedicated command group:
macros, eventtypes, tags, limits, authorize, and anything else under
``$SPLUNK_HOME/etc/*/local``. There is no blocklist — the dry-run guard
and ``--yes`` are the only safety net, consistent with the rest of the
CLI, so every ``set``/``unset``/``reload`` preview names the exact file
and stanza before applying.
"""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import conf_ops
from splunkctl.commands.common import app_scope, fetch_page, list_options, parse_set


def _not_found_message(exc: KeyError, file: str, stanza: str) -> str:
    """Render a not-found message, naming the file when that's what's missing.

    ``conf_ops.get_stanza``/``unset_keys`` do a two-step SDK lookup
    (``client.service.confs[file][stanza]``) and the underlying SDK raises
    ``KeyError(key)`` with whichever key 404'd — ``file`` when the conf
    file itself doesn't exist, ``stanza`` when the file exists but the
    stanza doesn't. Reuse that key to tell the two cases apart; fall back
    to the stanza-not-found phrasing when the key doesn't match either
    (e.g. a mock or SDK version that doesn't preserve it).
    """
    missing = exc.args[0] if exc.args else None
    if missing is not None and str(missing) == file:
        return f"Conf file '{file}.conf' not found."
    return f"Stanza '{stanza}' not found in {file}.conf."


@click.group("conf")
def conf_group() -> None:
    """Generic conf file/stanza editor (any conf, including sensitive ones)."""


@conf_group.command("files")
@click.option(
    "--app",
    default=None,
    help="Scope conf-file visibility to one app (default: current namespace).",
)
@list_options
@click.pass_context
def files(
    ctx: click.Context,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List conf files known to the server."""
    client = get_client(ctx)
    scope = app_scope(app)
    items = fetch_page(
        lambda **pg: client.service.confs.list(**scope, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows = [{"name": f.name} for f in items]
    output.render(ctx, rows, empty="No conf files found.")


@conf_group.command("list")
@click.argument("file")
@click.option(
    "--app",
    default=None,
    help="Only stanzas in this app (default: current namespace, which may "
    "miss app-private stanzas — pass --app to see them all).",
)
@list_options
@click.pass_context
def list_stanzas(
    ctx: click.Context,
    file: str,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List stanzas in a conf file."""
    client = get_client(ctx)
    scope = app_scope(app)
    items = fetch_page(
        lambda **pg: client.service.confs[file].list(**scope, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "app": dict(s.access).get("app", ""),
            "disabled": s.content.get("disabled", ""),
        }
        for s in items
    ]
    output.render(ctx, rows, empty=f"No stanzas found in {file}.conf.")


@conf_group.command("get")
@click.argument("file")
@click.argument("stanza")
@click.option(
    "--app",
    default=None,
    help="App to resolve the stanza in, when the same stanza exists in "
    "more than one app (default: current namespace).",
)
@click.option("--key", default=None, help="Show only this key's value.")
@click.pass_context
def get(
    ctx: click.Context, file: str, stanza: str, app: str | None, key: str | None
) -> None:
    """Show a conf stanza's keys, or one key's value with --key."""
    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, file, stanza, app=app)
    except KeyError as exc:
        output.error(_not_found_message(exc, file, stanza), kind="not_found")
        ctx.exit(1)
        return
    content: dict[str, Any] = dict(entity.content)
    if key is not None:
        output.render(ctx, {"name": entity.name, key: content.get(key, "")})
        return
    output.render(ctx, {"name": entity.name, **content})


@conf_group.command("set")
@guard.guarded
@click.argument("file")
@click.argument("stanza")
@click.argument("pairs", nargs=-1, required=True)
@click.pass_context
def set_keys(
    ctx: click.Context, file: str, stanza: str, pairs: tuple[str, ...]
) -> None:
    """Set KEY=VALUE pairs on a conf stanza (creates it if absent)."""
    kv = parse_set(pairs)
    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, file, stanza)
        current: dict[str, Any] = dict(entity.content)
    except KeyError:
        current = {}
    diff = "\n".join(conf_ops.diff_lines(current, kv))
    details = f"  file: {file}.conf\n  stanza: {stanza}\n{diff}"

    if not guard.check(
        ctx, f"Set {len(kv)} key(s) on '{stanza}' in {file}.conf", details=details
    ):
        return

    try:
        _, created = conf_ops.set_keys(client, file, stanza, kv)
    except KeyError as exc:
        output.error(_not_found_message(exc, file, stanza), kind="not_found")
        ctx.exit(1)
        return
    verb = "Created" if created else "Updated"
    output.info(f"{verb} {file} stanza '{stanza}' ({len(kv)} key(s)).")


@conf_group.command("unset")
@guard.guarded
@click.argument("file")
@click.argument("stanza")
@click.argument("keys", nargs=-1, required=True)
@click.pass_context
def unset_keys(
    ctx: click.Context, file: str, stanza: str, keys: tuple[str, ...]
) -> None:
    """Clear keys on a conf stanza (REST cannot delete a key; sets empty)."""
    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, file, stanza)
    except KeyError as exc:
        output.error(_not_found_message(exc, file, stanza), kind="not_found")
        ctx.exit(1)
        return
    current: dict[str, Any] = dict(entity.content)

    removals = "\n".join(f"  {k}: {current.get(k, '')} -> (empty)" for k in keys)
    details = f"  file: {file}.conf\n  stanza: {stanza}\n{removals}"
    if not guard.check(
        ctx, f"Clear {len(keys)} key(s) on '{stanza}' in {file}.conf", details=details
    ):
        return

    try:
        conf_ops.unset_keys(client, file, stanza, keys)
    except KeyError as exc:
        output.error(_not_found_message(exc, file, stanza), kind="not_found")
        ctx.exit(1)
        return
    output.info(
        f"Cleared {len(keys)} key(s) on '{stanza}' in {file}.conf "
        "(REST cannot remove conf keys; values set to empty)."
    )


@conf_group.command("reload")
@guard.guarded
@click.argument("file")
@click.pass_context
def reload_conf(ctx: click.Context, file: str) -> None:
    """Reload a conf file so its changes take effect."""
    if not guard.check(ctx, f"Reload conf: {file}"):
        return
    client = get_client(ctx)
    conf_ops.reload_conf(client, file)
    output.info(f"Reloaded: {file}.")
