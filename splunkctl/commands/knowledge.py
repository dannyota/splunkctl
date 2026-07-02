"""Macros / eventtypes / tags convenience verbs.

Thin, object-shaped wrappers over the generic `conf` group for the
knowledge objects detections lean on most: macros.conf, eventtypes.conf,
and tags.conf. `conf` remains the escape hatch for everything else
(and for anything these verbs don't cover) — these three groups exist
purely for a friendlier read shape (macro arg-form resolution, tags'
enabled-only summary) and, for macros, a guarded `set` that saves
writing out the raw stanza name by hand.

Only `macros set` mutates; `eventtypes` and `tags` are read-only —
tag/eventtype authoring stays on `conf set eventtypes|tags ...` until
a dedicated need for guarded writes shows up. Stanza access itself
(fetch/diff/create-or-update) is never re-implemented here — every
read and the one write go through `conf_ops`, the same core `conf`
uses.
"""

import re
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import conf_ops
from splunkctl.commands.common import app_scope, fetch_page, list_options, trunc

# Splunk's own naming for a parameterized macro stanza: `name(argcount)`.
_ARG_FORM = re.compile(r"^(?P<base>.+)\((?P<n>\d+)\)$")


# --------------------------------------------------------------------------
# macros
# --------------------------------------------------------------------------


@click.group("macros")
def macros_group() -> None:
    """Reusable SPL macro fragments (macros.conf)."""


@macros_group.command("list")
@click.option(
    "--app",
    default=None,
    help="Only macros in this app (default: current namespace, which may "
    "miss app-private macros — pass --app to see them all).",
)
@list_options
@click.pass_context
def macros_list(
    ctx: click.Context,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List macros with their definitions."""
    client = get_client(ctx)
    scope = app_scope(app)
    items = fetch_page(
        lambda **pg: client.service.confs["macros"].list(**scope, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    truncate = output.is_table(ctx)
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "definition": (
                trunc(s.content.get("definition", ""))
                if truncate
                else s.content.get("definition", "")
            ),
            "args": s.content.get("args", ""),
            "app": dict(s.access).get("app", ""),
        }
        for s in items
    ]
    output.render(ctx, rows, empty="No macros found.")


def _resolve_macro(client: Any, name: str, app: str | None) -> Any:
    """Resolve a macro name to its stanza entity.

    Tries an exact stanza match first — this alone handles a no-arg
    macro, and a caller that already spelled out the ``name(n)`` form.
    If that misses and ``name`` has no ``(n)`` suffix of its own, falls
    back to the macros.conf listing and picks the argument-form stanza
    whose base name matches; ties (more than one arg-count variant of
    the same base name, an unusual but legal macros.conf layout) break
    on the lowest arg count.

    Raises:
        KeyError: No stanza matches, with or without an arg-form.
    """
    try:
        return conf_ops.get_stanza(client, "macros", name, app=app)
    except KeyError:
        if "(" in name:
            raise
        candidates = [
            (int(m["n"]), s)
            for s in client.service.confs["macros"].list(**app_scope(app))
            if (m := _ARG_FORM.match(s.name)) and m["base"] == name
        ]
        if not candidates:
            raise
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0][1]


@macros_group.command("get")
@click.argument("name")
@click.option(
    "--app",
    default=None,
    help="App to resolve the macro in, when the same name exists in more "
    "than one app (default: current namespace).",
)
@click.pass_context
def macros_get(ctx: click.Context, name: str, app: str | None) -> None:
    """Show a macro's full stanza.

    ``name`` may be given with or without its ``(n)`` argument-count
    suffix — a bare name that has no no-arg stanza of its own resolves
    to its argument-form stanza automatically.
    """
    client = get_client(ctx)
    try:
        entity = _resolve_macro(client, name, app)
    except KeyError:
        output.error(f"Macro '{name}' not found in macros.conf.", kind="not_found")
        ctx.exit(1)
        return
    output.render(ctx, {"name": entity.name, **dict(entity.content)})


@macros_group.command("set")
@guard.guarded
@click.argument("name")
@click.option("--definition", required=True, help="SPL macro definition.")
@click.option(
    "--args",
    "args_csv",
    default=None,
    help="Comma-separated argument names — writes the argument-form "
    "stanza 'name(n)' (n = arg count) instead of the bare name.",
)
@click.pass_context
def macros_set(
    ctx: click.Context, name: str, definition: str, args_csv: str | None
) -> None:
    """Create or update a macro (delegates to conf_ops.set_keys on macros.conf).

    To update an existing argument-form macro, pass --args with the
    same arg count so the computed stanza name matches it — this is a
    thin name-to-stanza mapping, not a lookup against what already
    exists. For anything the mapping can't reach (e.g. changing a
    macro's arg count), use `conf set macros "name(n)" ...` directly.
    """
    args_list = [a.strip() for a in args_csv.split(",")] if args_csv else None
    stanza = f"{name}({len(args_list)})" if args_list else name
    kv: dict[str, str] = {"definition": definition}
    if args_list is not None:
        kv["args"] = ",".join(args_list)

    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, "macros", stanza)
        current: dict[str, Any] = dict(entity.content)
    except KeyError:
        current = {}
    diff = "\n".join(conf_ops.diff_lines(current, kv))
    details = f"  file: macros.conf\n  stanza: {stanza}\n{diff}"

    if not guard.check(
        ctx, f"Set {len(kv)} key(s) on '{stanza}' in macros.conf", details=details
    ):
        return

    _, created = conf_ops.set_keys(client, "macros", stanza, kv)
    verb = "Created" if created else "Updated"
    output.info(f"{verb} macro '{stanza}' ({len(kv)} key(s)).")


# --------------------------------------------------------------------------
# eventtypes (read-only)
# --------------------------------------------------------------------------


@click.group("eventtypes")
def eventtypes_group() -> None:
    """Event classification rules (eventtypes.conf) — read-only.

    Use `conf set eventtypes ...` / `conf unset eventtypes ...` to
    author or edit an eventtype.
    """


@eventtypes_group.command("list")
@click.option(
    "--app",
    default=None,
    help="Only eventtypes in this app (default: current namespace, which "
    "may miss app-private eventtypes — pass --app to see them all).",
)
@list_options
@click.pass_context
def eventtypes_list(
    ctx: click.Context,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List eventtypes with their search and disabled state."""
    client = get_client(ctx)
    scope = app_scope(app)
    items = fetch_page(
        lambda **pg: client.service.confs["eventtypes"].list(**scope, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    truncate = output.is_table(ctx)
    rows: list[dict[str, Any]] = [
        {
            "name": s.name,
            "search": (
                trunc(s.content.get("search", ""))
                if truncate
                else s.content.get("search", "")
            ),
            "app": dict(s.access).get("app", ""),
            "disabled": s.content.get("disabled", ""),
        }
        for s in items
    ]
    output.render(ctx, rows, empty="No eventtypes found.")


@eventtypes_group.command("get")
@click.argument("name")
@click.option(
    "--app",
    default=None,
    help="App to resolve the eventtype in, when the same name exists in "
    "more than one app (default: current namespace).",
)
@click.pass_context
def eventtypes_get(ctx: click.Context, name: str, app: str | None) -> None:
    """Show an eventtype's full stanza (search, tags, priority, color)."""
    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, "eventtypes", name, app=app)
    except KeyError:
        output.error(
            f"Eventtype '{name}' not found in eventtypes.conf.", kind="not_found"
        )
        ctx.exit(1)
        return
    output.render(ctx, {"name": entity.name, **dict(entity.content)})


# --------------------------------------------------------------------------
# tags (read-only)
# --------------------------------------------------------------------------

# tags.conf stanzas are named `<field>=<value>` (e.g. `eventtype=cim:auth`);
# each key inside the stanza is a tag name whose value is enabled/disabled.
# `disabled` itself is the stanza-level flag, not a tag, and eai:* keys are
# read-only REST metadata — both are excluded from the tag-name views below.
_TAG_METADATA_KEYS = {"disabled"}


def _is_tag_key(key: str) -> bool:
    return key not in _TAG_METADATA_KEYS and not key.startswith("eai:")


def _enabled_tag_names(content: dict[str, Any]) -> list[str]:
    """Tag names whose value is enabled, sorted for deterministic output."""
    return sorted(
        k for k, v in content.items() if _is_tag_key(k) and str(v) != "disabled"
    )


def _tag_states(content: dict[str, Any]) -> dict[str, Any]:
    """All tag-name -> enabled/disabled pairs on a stanza."""
    return {k: v for k, v in content.items() if _is_tag_key(k)}


@click.group("tags")
def tags_group() -> None:
    """CIM/eventtype tag assignments (tags.conf) — read-only.

    Use `conf set tags ...` / `conf unset tags ...` to author or edit a
    tag assignment.
    """


@tags_group.command("list")
@click.option(
    "--app",
    default=None,
    help="Only tag stanzas in this app (default: current namespace, which "
    "may miss app-private stanzas — pass --app to see them all).",
)
@list_options
@click.pass_context
def tags_list(
    ctx: click.Context,
    *,
    app: str | None,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List tags.conf stanzas with their enabled tag names.

    One row per ``field=value`` stanza; only enabled tags are shown —
    use ``tags get`` for a stanza's full enabled/disabled breakdown.
    """
    client = get_client(ctx)
    scope = app_scope(app)
    items = fetch_page(
        lambda **pg: client.service.confs["tags"].list(**scope, **pg),
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows: list[dict[str, Any]] = [
        {
            "field_value": s.name,
            "tags": ";".join(_enabled_tag_names(dict(s.content))),
            "app": dict(s.access).get("app", ""),
        }
        for s in items
    ]
    output.render(ctx, rows, empty="No tags found.")


@tags_group.command("get")
@click.argument("field_value")
@click.option(
    "--app",
    default=None,
    help="App to resolve the stanza in, when the same field=value exists "
    "in more than one app (default: current namespace).",
)
@click.pass_context
def tags_get(ctx: click.Context, field_value: str, app: str | None) -> None:
    """Show a tags.conf stanza's tag keys and their enabled/disabled state."""
    client = get_client(ctx)
    try:
        entity = conf_ops.get_stanza(client, "tags", field_value, app=app)
    except KeyError:
        output.error(
            f"Stanza '{field_value}' not found in tags.conf.", kind="not_found"
        )
        ctx.exit(1)
        return
    output.render(ctx, {"name": entity.name, **_tag_states(dict(entity.content))})
