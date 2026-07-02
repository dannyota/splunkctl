"""Shared helpers for command groups."""

import click


def parse_set(pairs: tuple[str, ...]) -> dict[str, str]:
    """Parse repeatable ``--set KEY=VALUE`` options into a dict.

    Values may contain ``=``; the split happens on the first one.

    Raises:
        click.BadParameter: On a pair without ``=`` or a read-only key.
    """
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        key = key.strip()
        if not sep or not key:
            raise click.BadParameter(f"expected KEY=VALUE, got '{pair}'")
        if key.startswith("eai:"):
            raise click.BadParameter(f"'{key}' is read-only")
        out[key] = value
    return out
