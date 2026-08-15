"""Auto-generate MCP tool schemas from the Click command tree."""

from typing import Any

import click

from splunkctl.guard import is_guarded

# Global flags live on the root group only (main._CLI hoists them from
# the token stream) — leaf commands never carry them, so the only names
# to skip are Click's own help and the guard's yes (re-added per schema).
SKIP_PARAMS = frozenset({"help", "yes"})

# Internal/maintainer groups that never become MCP tools.
INTERNAL_GROUPS = frozenset(
    {"mcp", "commands", "skill", "config", "doctor", "info", "docs", "auth"}
)

_YES_PROP: dict[str, Any] = {
    "type": "boolean",
    "default": False,
    "description": "Apply the mutation (omit or false = dry-run preview).",
}


def _param_schema(p: click.Parameter) -> dict[str, Any] | None:
    """Convert a Click parameter to a JSON Schema property."""
    if p.name in SKIP_PARAMS:
        return None
    if isinstance(p, click.Option) and p.hidden:
        return None

    prop: dict[str, Any] = {}
    if isinstance(p.type, click.Choice):
        prop["type"] = "string"
        prop["enum"] = list(p.type.choices)
    elif isinstance(p.type, (click.IntRange, click.types.IntParamType)):
        prop["type"] = "integer"
    elif isinstance(p.type, (click.FloatRange, click.types.FloatParamType)):
        prop["type"] = "number"
    elif isinstance(p.type, click.types.BoolParamType):
        prop["type"] = "boolean"
    elif isinstance(p, click.Option) and p.is_flag:
        prop["type"] = "boolean"
    else:
        prop["type"] = "string"

    multi = (isinstance(p, click.Option) and p.multiple) or (
        isinstance(p, click.Argument) and p.nargs == -1
    )
    if multi:
        prop = {"type": "array", "items": prop}

    if isinstance(p, click.Option) and p.help:
        prop["description"] = p.help
    elif isinstance(p, click.Argument) and p.type.name != "TEXT":
        prop["description"] = p.type.name

    if (
        isinstance(p, click.Option)
        and not p.is_flag
        and p.default is not None
        and isinstance(p.default, str | int | float)
    ):
        prop["default"] = p.default

    return prop


type ToolIndex = dict[str, "ToolEntry"]


class ToolEntry:
    """A single tool derived from a Click command."""

    __slots__ = (
        "name",
        "description",
        "schema",
        "cmd_path",
        "guarded",
        "positional",
        "arg_order",
        "flags",
        "neg_flags",
    )

    def __init__(  # noqa: D107
        self,
        name: str,
        description: str,
        schema: dict[str, Any],
        cmd_path: list[str],
        *,
        guarded: bool = False,
        positional: frozenset[str] = frozenset(),
        arg_order: tuple[str, ...] = (),
        flags: dict[str, str] | None = None,
        neg_flags: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.cmd_path = cmd_path
        self.guarded = guarded
        self.positional = positional
        self.arg_order = arg_order
        self.flags = flags or {}
        self.neg_flags = neg_flags or {}


def _tool_name(path: list[str]) -> str:
    """Build an underscore-separated tool name from a command path."""
    return "_".join(seg.replace("-", "_") for seg in path)


def _long_flag(p: click.Option) -> str | None:
    """Return the option's canonical long CLI flag (``--like-this``)."""
    longs = [o for o in p.opts if o.startswith("--")]
    if longs:
        return longs[0]
    return p.opts[0] if p.opts else None


def _make_entry(cmd: click.Command, path: list[str]) -> ToolEntry:
    """Build a ToolEntry (schema, positional order, guard) for one command."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    pos: list[str] = []
    flags: dict[str, str] = {}
    neg_flags: dict[str, str] = {}
    for p in cmd.params:
        if p.name is None:
            continue
        prop = _param_schema(p)
        if prop is None:
            continue
        # Schema names come from the Python param name; a trailing
        # underscore (keyword-avoidance like ``wait_``) is stripped for
        # callers — the flag map below keeps invocation correct either way.
        pname = p.name.replace("-", "_")
        display = pname.rstrip("_") or pname
        if display in properties:
            display = pname
        properties[display] = prop
        if isinstance(p, click.Argument):
            required.append(display)
            pos.append(display)
            continue
        if isinstance(p, click.Option):
            flag = _long_flag(p)
            if flag is not None:
                flags[display] = flag
            if p.secondary_opts:
                neg = [o for o in p.secondary_opts if o.startswith("--")]
                if neg:
                    neg_flags[display] = neg[0]
            if p.required or p.prompt:
                # prompt=True options would hang the MCP subprocess waiting
                # for TTY input, so force callers to always supply them.
                required.append(display)

    guarded = is_guarded(cmd)
    if guarded:
        properties["yes"] = dict(_YES_PROP)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required

    desc = (cmd.help or "").split("\n")[0]
    if guarded:
        desc += " [guarded: dry-run by default, pass yes=true to apply]"

    return ToolEntry(
        name=_tool_name(path),
        description=desc,
        schema=schema,
        cmd_path=path,
        guarded=guarded,
        positional=frozenset(pos),
        arg_order=tuple(pos),
        flags=flags,
        neg_flags=neg_flags,
    )


def _walk_commands(
    group: click.Group,
    prefix: list[str],
    index: ToolIndex,
) -> None:
    """Recursively walk the Click tree and build tool entries."""
    for name, cmd in sorted(group.commands.items()):
        path = [*prefix, name]
        if isinstance(cmd, click.Group):
            _walk_commands(cmd, path, index)
            continue
        entry = _make_entry(cmd, path)
        index[entry.name] = entry


def build_tool_index(root: click.Group) -> ToolIndex:
    """Build a full tool index from the CLI root group.

    Skips internal groups (mcp, commands, skill, config, doctor, info, docs).
    """
    index: ToolIndex = {}
    for name, cmd in sorted(root.commands.items()):
        if name in INTERNAL_GROUPS:
            continue
        if isinstance(cmd, click.Group):
            _walk_commands(cmd, [name], index)
        else:
            entry = _make_entry(cmd, [name])
            index[entry.name] = entry
    return index


def group_names(root: click.Group) -> list[str]:
    """Return the names of top-level command groups (excluding internals)."""
    return sorted(
        name
        for name, cmd in root.commands.items()
        if isinstance(cmd, click.Group) and name not in INTERNAL_GROUPS
    )


def group_tools(index: ToolIndex, group: str) -> list[ToolEntry]:
    """Return all tools under a group or subgroup path.

    Accepts space-separated paths (``"soar containers"``) as well as
    plain group names (``"indexes"``).
    """
    prefix = group.replace(" ", "_").replace("-", "_") + "_"
    return [t for t in index.values() if t.name.startswith(prefix)]


def subgroup_names(root: click.Group, group: str) -> list[str]:
    """Return subgroup names within a top-level group.

    For ``soar`` this yields ``["actions", "apps", "artifacts", ...]`` —
    only the children that are themselves ``click.Group`` instances.
    """
    top = root.commands.get(group)
    if not isinstance(top, click.Group):
        return []
    return sorted(
        name for name, cmd in top.commands.items() if isinstance(cmd, click.Group)
    )


def has_subgroups(root: click.Group, group: str) -> bool:
    """Return True if the group has nested subgroups."""
    return bool(subgroup_names(root, group))


def leaf_count(cmd: click.Command) -> int:
    """Count leaf commands, recursing into nested subgroups.

    Matches the number of typed tools a full focus of the group would
    load — a nested subgroup counts its commands, not itself.
    """
    if not isinstance(cmd, click.Group):
        return 1
    return sum(leaf_count(c) for c in cmd.commands.values())


def direct_commands(root: click.Group, group: str) -> list[str]:
    """Return direct (non-group) command names under a top-level group."""
    top = root.commands.get(group)
    if not isinstance(top, click.Group):
        return []
    return sorted(
        name for name, cmd in top.commands.items() if not isinstance(cmd, click.Group)
    )


def group_summary(root: click.Group) -> list[dict[str, str]]:
    """Build a summary of command groups with descriptions and counts.

    Groups that contain nested subgroups (like ``soar``) include a
    ``subgroups`` key with the two-level layout so agents can discover
    subgroup focus paths without flooding context.
    """
    rows: list[dict[str, str]] = []
    for name, cmd in sorted(root.commands.items()):
        if name in INTERNAL_GROUPS:
            continue
        if isinstance(cmd, click.Group):
            subs = list(cmd.commands.keys())
            desc = (cmd.help or "").split("\n")[0]
            row: dict[str, str] = {
                "group": name,
                "description": desc,
                "subcommands": ", ".join(sorted(subs)),
                "count": str(leaf_count(cmd)),
            }
            sg = subgroup_names(root, name)
            if sg:
                row["subgroups"] = ", ".join(sg)
            rows.append(row)
    return rows
