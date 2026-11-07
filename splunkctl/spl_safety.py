"""Recognize explicit SPL write commands before dispatch."""

import re

import click

WRITE_COMMANDS = frozenset(
    {
        "outputlookup",
        "collect",
        "mcollect",
        "meventcollect",
        "sendalert",
        "delete",
        "outputcsv",
        "outputtext",
        "sendemail",
        "runshellscript",
        "script",
    }
)
_TOKENS = re.compile(
    r'```[\s\S]*?(?:```|$)|"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'|[|\[\]]|[A-Za-z_][A-Za-z_0-9]*|[^\s]",
)


def find_write_commands(spl: str) -> list[str]:
    """Return distinct write commands in pipeline order, ignoring literals."""
    found: list[str] = []
    leading = True
    for match in _TOKENS.finditer(spl):
        part = match.group()
        if part.startswith("```"):
            continue
        if part in ("|", "["):
            leading = True
        elif part == "]":
            leading = False
        elif leading:
            command = part.lower()
            if command == "search":
                continue
            if command in WRITE_COMMANDS and command not in found:
                found.append(command)
            leading = False
    return found


def check_spl(ctx: click.Context, spl: str) -> bool:
    """Refuse explicit write SPL during a dry run."""
    commands = find_write_commands(spl)
    if commands and ctx.obj.get("dry_run", True):
        click.echo(
            f"[DRY RUN] SPL contains write command(s): {', '.join(commands)}. "
            "Pass --yes to run it.",
            err=True,
        )
        return False
    return True
