"""Shared SOAR client construction for command modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from splunkctl import config as cfg_mod
from splunkctl import output
from splunkctl.soar.client import SOARClient


def get_soar_client(ctx: click.Context) -> SOARClient:
    """Build a SOARClient from the resolved SOAR config.

    Raises ``SystemExit(1)`` with a ``usage`` error envelope when no
    SOAR host is configured.
    """
    obj: dict[str, Any] = ctx.obj or {}
    cfg_path = obj.get("config")
    profile = obj.get("profile")
    config_path = Path(cfg_path) if cfg_path else None
    cfg = cfg_mod.resolve_soar(config_path, profile=profile)

    host = cfg.get("host")
    if not host:
        output.error(
            "No SOAR host configured. Run 'splunkctl config init --soar' "
            "or set SOAR_HOST.",
            kind="usage",
        )
        ctx.exit(1)
        raise SystemExit(1)  # unreachable after ctx.exit in real Click

    return SOARClient(
        host=host,
        port=int(cfg.get("port", 8443)),
        token=cfg.get("token"),
        username=cfg.get("username"),
        password=cfg.get("password"),
        verify=bool(cfg.get("verify", False)),
    )
