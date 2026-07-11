"""Mutation guard — dry-run preview, --yes to apply."""

from pathlib import Path
from typing import Any

import click

from splunkctl import config as cfg_mod


def soar_banner(ctx: click.Context) -> str:
    """Build ``(SOAR @ host:port)`` guard banner for SOAR mutations.

    Reads SOAR config via :func:`splunkctl.config.resolve_soar` — no
    network I/O. Safe for dry-run previews and ``--yes`` confirmations.
    """
    obj: dict[str, Any] = ctx.obj or {}
    config_path = Path(obj["config"]) if obj.get("config") else None
    cfg = cfg_mod.resolve_soar(config_path, profile=obj.get("profile"))
    host = cfg.get("host", "unknown")
    port = cfg.get("port", 8443)
    return f"(SOAR @ {host}:{port})"


def soar_check(ctx: click.Context, action: str, *, details: str = "") -> bool:
    """SOAR mutation guard — same as :func:`check` but with the SOAR banner."""
    obj: dict[str, Any] = ctx.obj or {}
    tag = soar_banner(ctx)

    if not obj.get("dry_run", True):
        click.echo(f"Applying: {action} {tag}", err=True)
        return True

    click.echo(f"[DRY RUN] {action} {tag}", err=True)
    if details:
        click.echo(details, err=True)
    click.echo("Pass --yes to apply.", err=True)
    return False


def banner(ctx: click.Context, *, overrides: dict[str, Any] | None = None) -> str:
    """Build the ``(source: name @ host:port)`` guard banner.

    Reads only local config (file + env) via :func:`splunkctl.config.resolve`
    — never constructs a ``SplunkClient`` or performs auth. Safe to call
    before every mutation preview and ``--yes`` confirmation, so help/offline
    commands and dry-run previews alike stay lazy-auth compliant.

    Args:
        ctx: Click context carrying ``config``/``profile`` global flags.
        overrides: CLI-flag-provided connection fields, if any (mirrors
            :class:`splunkctl.client.SplunkClient`'s override layer).

    Raises:
        splunkctl.config.ProfileNotFoundError: the selected profile does
            not exist.
    """
    obj: dict[str, Any] = ctx.obj or {}
    config_path = Path(obj["config"]) if obj.get("config") else None
    resolved = cfg_mod.resolve(
        config_path, profile=obj.get("profile"), overrides=overrides
    )
    cfg = resolved["cfg"]
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 8089)
    label = (
        f"profile: {resolved['profile']}"
        if resolved["source"] == "profile"
        else resolved["source"]
    )
    return f"({label} @ {host}:{port})"


def check(ctx: click.Context, action: str, *, details: str = "") -> bool:
    """Return True if the mutation should proceed.

    Dry-run (default) prints a preview to stderr and returns False.
    Pass ``--yes`` to apply. Both the preview and the ``--yes``
    confirmation carry the active profile/host banner, so an agent can
    never mistake which instance it's about to mutate (e.g. UAT vs prod).
    """
    obj: dict[str, Any] = ctx.obj or {}
    tag = banner(ctx)

    if not obj.get("dry_run", True):
        click.echo(f"Applying: {action} {tag}", err=True)
        return True

    click.echo(f"[DRY RUN] {action} {tag}", err=True)
    if details:
        click.echo(details, err=True)
    click.echo("Pass --yes to apply.", err=True)
    return False


def banner_soar(ctx: click.Context) -> str:
    """Build the ``(SOAR @ host:port)`` guard banner for SOAR mutations."""
    obj: dict[str, Any] = ctx.obj or {}
    config_path = Path(obj["config"]) if obj.get("config") else None
    cfg = cfg_mod.resolve_soar(config_path, profile=obj.get("profile"))
    host = cfg.get("host", "soar-host")
    port = cfg.get("port", 8443)
    return f"(SOAR @ {host}:{port})"


def check_soar(ctx: click.Context, action: str, *, details: str = "") -> bool:
    """Return True if the SOAR mutation should proceed.

    Same contract as :func:`check` but uses SOAR config for the banner.
    """
    obj: dict[str, Any] = ctx.obj or {}
    tag = banner_soar(ctx)

    if not obj.get("dry_run", True):
        click.echo(f"Applying: {action} {tag}", err=True)
        return True

    click.echo(f"[DRY RUN] {action} {tag}", err=True)
    if details:
        click.echo(details, err=True)
    click.echo("Pass --yes to apply.", err=True)
    return False


def guarded[F](cmd: F) -> F:
    """Mark a Click command callback as a guarded mutation."""
    cmd.guarded = True  # type: ignore[attr-defined]
    return cmd


def is_guarded(cmd: click.Command) -> bool:
    """Check whether a command is a guarded mutation."""
    if getattr(cmd, "guarded", False):
        return True
    cb = getattr(cmd, "callback", None)
    return bool(getattr(cb, "guarded", False)) if cb else False
