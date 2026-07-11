"""Auto-generate MCP tool schemas from the Click command tree."""

from typing import Any

import click

from splunkctl.guard import is_guarded

SKIP_PARAMS = frozenset(
    {
        "help",
        "json",
        "use_json",
        "fmt",
        "format",
        "fields",
        "out",
        "debug",
        "timeout",
        "config",
        "profile",
        "yes",
    }
)

_YES_PROP: dict[str, Any] = {
    "type": "boolean",
    "default": False,
    "description": "Apply the mutation (omit or false = dry-run preview).",
}


def _param_schema(p: click.Parameter) -> dict[str, Any] | None:
    """Convert a Click parameter to a JSON Schema property."""
    if p.name in SKIP_PARAMS or p.name == "help":
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
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.cmd_path = cmd_path
        self.guarded = guarded
        self.positional = positional
        self.arg_order = arg_order


def _tool_name(path: list[str]) -> str:
    """Build an underscore-separated tool name from a command path."""
    return "_".join(seg.replace("-", "_") for seg in path)


def _make_entry(cmd: click.Command, path: list[str]) -> ToolEntry:
    """Build a ToolEntry (schema, positional order, guard) for one command."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    pos: list[str] = []
    for p in cmd.params:
        if p.name is None:
            continue
        prop = _param_schema(p)
        if prop is None:
            continue
        pname = p.name.replace("-", "_")
        properties[pname] = prop
        if isinstance(p, click.Argument):
            required.append(pname)
            pos.append(pname)
        elif isinstance(p, click.Option) and (p.required or p.prompt):
            # prompt=True options would hang the MCP subprocess waiting
            # for TTY input, so force callers to always supply them.
            required.append(pname)

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

    Skips internal groups (mcp, commands, skill, config, doctor, info).
    """
    skip = {"mcp", "commands", "skill", "config", "doctor", "info"}
    index: ToolIndex = {}
    for name, cmd in sorted(root.commands.items()):
        if name in skip:
            continue
        if isinstance(cmd, click.Group):
            _walk_commands(cmd, [name], index)
        else:
            entry = _make_entry(cmd, [name])
            index[entry.name] = entry
    return index


def group_names(root: click.Group) -> list[str]:
    """Return the names of top-level command groups (excluding internals)."""
    skip = {"mcp", "commands", "skill", "config", "doctor", "info"}
    return sorted(
        name
        for name, cmd in root.commands.items()
        if isinstance(cmd, click.Group) and name not in skip
    )


def group_tools(index: ToolIndex, group: str) -> list[ToolEntry]:
    """Return all tools under a given top-level group."""
    prefix = group.replace("-", "_") + "_"
    return [t for t in index.values() if t.name.startswith(prefix)]


def group_summary(root: click.Group) -> list[dict[str, str]]:
    """Build a summary of command groups with descriptions and counts."""
    skip = {"mcp", "commands", "skill", "config", "doctor", "info"}
    rows: list[dict[str, str]] = []
    for name, cmd in sorted(root.commands.items()):
        if name in skip:
            continue
        if isinstance(cmd, click.Group):
            subs = list(cmd.commands.keys())
            desc = (cmd.help or "").split("\n")[0]
            rows.append(
                {
                    "group": name,
                    "description": desc,
                    "subcommands": ", ".join(sorted(subs)),
                    "count": str(len(subs)),
                }
            )
    return rows
