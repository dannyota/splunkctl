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

    if cfg.get("auth_mode") == "browser":
        from splunkctl.auth import adapters
        from splunkctl.auth import session as sess_mod

        ta = sess_mod.resolve_target(config_path, profile, "soar")
        rec = sess_mod.load(ta.profile, "soar", expected_origin=ta.web_url)
        if rec is None:
            output.error(
                "SOAR browser session is missing. Run "
                "`splunkctl auth login --target soar`.",
                kind="auth",
            )
            ctx.exit(1)
        status = adapters.get_adapter("soar").validate(
            rec.values, api_base=ta.api_base, verify=ta.verify, timeout=30
        )
        if status == "expired":
            sess_mod.delete(ta.profile, "soar")
            output.error(
                "SOAR browser session expired. Run "
                "`splunkctl auth login --target soar`.",
                kind="auth",
            )
            ctx.exit(1)
        if status == "unreachable":
            output.error(
                "SOAR is unreachable while checking the browser session.",
                kind="connection",
            )
            ctx.exit(1)
        return SOARClient(
            host=host,
            port=int(cfg.get("port", 8443)),
            verify=bool(cfg.get("verify", False)),
            cookies=rec.values,
        )

    return SOARClient(
        host=host,
        port=int(cfg.get("port", 8443)),
        token=cfg.get("token"),
        username=cfg.get("username"),
        password=cfg.get("password"),
        verify=bool(cfg.get("verify", False)),
    )
