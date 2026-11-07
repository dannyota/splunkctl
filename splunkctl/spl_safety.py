"""Recognize explicit SPL write commands before dispatch."""

import re

import click

from splunkctl import output

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
    r"|'(?:\\.|[^'\\])*'|`[^`]*`|[|\[\]]|[A-Za-z_][A-Za-z_0-9]*|[^\s]",
)


def find_write_commands(spl: str) -> list[str]:
    """Return distinct write commands in pipeline order, ignoring literals."""
    found: list[str] = []
    leading = False
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
            leading = False
            comparison = spl[match.end() :].lstrip().startswith("=")
            if not comparison and command in WRITE_COMMANDS and command not in found:
                found.append(command)
    return found


def check_spl(ctx: click.Context, spl: str) -> bool:
    """Refuse explicit write SPL during a dry run."""
    commands = find_write_commands(spl)
    if commands and ctx.obj.get("dry_run", True):
        message = (
            f"[DRY RUN] SPL contains write command(s): {', '.join(commands)}. "
            "Pass --yes to run it."
        )
        if output._json_errors():
            output.error(message, kind="confirmation_required")
        else:
            click.echo(message, err=True)
        ctx.exit(1)
    return True
