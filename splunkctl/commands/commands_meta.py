"""Self-discovery — machine-readable command tree for agents."""

import json
from typing import Any

import click

from splunkctl import __version__, output
from splunkctl.guard import is_guarded


def _param_entry(p: click.Parameter) -> dict[str, Any]:
    """Build a single parameter descriptor."""
    entry: dict[str, Any] = {
        "name": p.name or "",
        "type": p.type.name if hasattr(p.type, "name") else str(p.type),
    }
    if isinstance(p, click.Argument):
        entry["kind"] = "argument"
    elif isinstance(p, click.Option):
        entry["kind"] = "option"
        if p.opts:
            entry["flags"] = p.opts
        if p.is_flag:
            entry["type"] = "flag"
        if p.required:
            entry["required"] = True
        if p.help:
            entry["help"] = p.help
    if isinstance(p.type, click.Choice):
        entry["choices"] = list(p.type.choices)
    if not (isinstance(p, click.Option) and p.is_flag):
        if isinstance(p.default, (str, int, float)) and p.default is not None:
            entry["default"] = p.default
    return entry


def _walk(group: click.Group) -> list[dict[str, Any]]:
    """Recursively build the command tree."""
    nodes: list[dict[str, Any]] = []
    for name, cmd in sorted(group.commands.items()):
        if cmd.hidden:
            continue
        node: dict[str, Any] = {
            "name": name,
            "help": (cmd.help or "").split("\n")[0],
        }
        if isinstance(cmd, click.Group):
            node["subcommands"] = _walk(cmd)
        else:
            if is_guarded(cmd):
                node["guarded"] = True
            params: list[dict[str, Any]] = []
            for p in cmd.params:
                if p.name in ("help",):
                    continue
                params.append(_param_entry(p))
            if params:
                node["params"] = params
        nodes.append(node)
    return nodes


@click.command("commands")
@click.pass_context
def commands_meta(ctx: click.Context) -> None:
    """Print the command tree as JSON (for agent discovery)."""
    root = ctx.parent
    if root is None or not isinstance(root.command, click.Group):
        output.error("Cannot resolve CLI root.")
        ctx.exit(1)
        return
    global_opts = [
        _param_entry(p) for p in root.command.params if p.name not in ("help",)
    ]
    result: dict[str, Any] = {
        "version": __version__,
        "global_options": global_opts,
        "note": "guarded commands are dry-run by default; pass --yes to apply",
        "commands": _walk(root.command),
    }
    click.echo(json.dumps(result, indent=2))
