"""Recognize explicit SPL write commands before dispatch."""

import re
from collections.abc import Callable, Iterable
from typing import Any

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
    from splunkctl.request_context import readonly

    if readonly():
        from splunkctl.commands.search import _normalize_spl

        check_readonly_spl(_normalize_spl(spl), expand=False)
        return True
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


DYNAMIC_COMMANDS = frozenset({"map", "savedsearch", "dbxquery", "dbxoutput", "run"})


def _read_commands(spl: str) -> tuple[list[str], bool]:
    """Tokenize command positions and refuse ambiguous SPL syntax."""
    from splunkctl.request_policy import ReadOnlyError

    commands: list[str] = []
    leading = True
    depth = 0
    expansion = False
    for match in _TOKENS.finditer(spl):
        part = match.group()
        if part.startswith("```"):
            if not part.endswith("```") or len(part) < 6:
                raise ReadOnlyError("malformed SPL comment")
            continue
        if part.startswith("`"):
            expansion = True
            leading = False
            continue
        if part.startswith(('"', "'")):
            if len(part) == 1 or part[-1] != part[0]:
                raise ReadOnlyError("malformed SPL literal")
            if leading:
                raise ReadOnlyError("malformed SPL command")
            continue
        if part == "|":
            if leading and commands:
                raise ReadOnlyError("malformed SPL pipeline")
            leading = True
        elif part == "[":
            depth += 1
            expansion = True
            leading = True
        elif part == "]":
            depth -= 1
            if depth < 0 or leading:
                raise ReadOnlyError("malformed SPL subsearch")
            leading = False
        elif leading:
            command = part.lower()
            if not re.fullmatch(r"[a-z_][a-z_0-9]*", command):
                raise ReadOnlyError("malformed SPL command")
            comparison = spl[match.end() :].lstrip().startswith("=")
            commands.append("search" if comparison else command)
            leading = False
    if leading or depth:
        raise ReadOnlyError("malformed SPL")
    return commands, expansion


def check_readonly_spl(
    spl: str, *, parser: Callable[[str], Any] | None = None, expand: bool = True
) -> None:
    """Fail closed on writers, dynamic commands and unknown command names."""
    from splunkctl.request_policy import ReadOnlyError
    from splunkctl.spl_read_commands import READ_COMMANDS

    commands, expansion = _read_commands(spl)

    def check(names: Iterable[str]) -> None:
        for name in names:
            if name == "rest":
                raise ReadOnlyError(
                    "SPL command rest is refused; use `splunkctl api get` instead"
                )
            if (
                name in WRITE_COMMANDS
                or name in DYNAMIC_COMMANDS
                or name not in READ_COMMANDS
            ):
                raise ReadOnlyError(f"SPL command {name} is refused")

    check(find_write_commands(spl))
    check(commands)
    if expansion and expand:
        if parser is None:
            raise ReadOnlyError("SPL expansion requires the search/parser endpoint")
        try:
            result = parser(spl)
            expanded = result["commands"]
            if not isinstance(expanded, list) or not expanded:
                raise ValueError("missing expanded commands")
            names = [entry["command"].lower() for entry in expanded]
            check(names)
        except ReadOnlyError:
            raise
        except Exception as exc:
            raise ReadOnlyError(
                "search/parser failed to classify expanded SPL"
            ) from exc
