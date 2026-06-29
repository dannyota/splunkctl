"""Mutation guard — dry-run preview, --yes to apply."""

from typing import Any

import click


def check(ctx: click.Context, action: str, *, details: str = "") -> bool:
    """Return True if the mutation should proceed.

    Dry-run (default) prints a preview to stderr and returns False.
    Pass ``--yes`` to apply.
    """
    obj: dict[str, Any] = ctx.obj or {}
    if not obj.get("dry_run", True):
        return True

    click.echo(f"[DRY RUN] {action}", err=True)
    if details:
        click.echo(details, err=True)
    click.echo("Pass --yes to apply.", err=True)
    return False
