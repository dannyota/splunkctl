"""Read-only MCP discovery and command resolution."""

import copy
import os

import click

from splunkctl.guard import is_guarded


def enabled(setting: bool = False) -> bool:
    """Combine settings without allowing a weaker setting to disable policy."""
    from splunkctl.request_context import readonly

    return (
        setting
        or readonly()
        or os.getenv("SPLUNKCTL_READ_ONLY", "").lower() in {"1", "true", "yes"}
    )


def mutation(cmd: click.Command, path: tuple[str, ...]) -> bool:
    """Identify guarded server writes and authentication commands."""
    return is_guarded(cmd) or path in {("auth", "login"), ("auth", "logout")}


def read_tree(root: click.Group, path: tuple[str, ...] = ()) -> click.Group:
    """Copy the command tree with server mutations removed from discovery."""
    result = copy.copy(root)
    result.commands = {}
    for name, cmd in root.commands.items():
        child_path = (*path, name)
        if mutation(cmd, child_path):
            continue
        if isinstance(cmd, click.Group):
            child = read_tree(cmd, child_path)
            if child.commands:
                result.commands[name] = child
        else:
            result.commands[name] = cmd
    return result


def command_mutates(root: click.Group, tokens: list[str]) -> bool:
    """Resolve Click options and nested groups before executing a raw command.

    Unresolvable syntax fails closed; the CLI still accepts local commands.
    """
    cmd: click.Command = root
    path: tuple[str, ...] = ()
    parent: click.Context | None = None
    args = tokens
    contexts: list[click.Context] = []
    try:
        while isinstance(cmd, click.Group):
            ctx = cmd.make_context(cmd.name or "splunkctl", args, parent=parent)
            contexts.append(ctx)
            remaining = [*ctx._protected_args, *ctx.args]
            if not remaining:
                return False
            name, child, args = cmd.resolve_command(ctx, remaining)
            if child is None or name is None:
                return True
            path = (*path, name)
            if mutation(child, path):
                return True
            parent = ctx
            cmd = child
        return mutation(cmd, path)
    except (click.ClickException, click.exceptions.Exit):
        return True
    finally:
        for ctx in reversed(contexts):
            ctx.close()
