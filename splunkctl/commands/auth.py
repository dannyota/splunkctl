"""Browser SAML authentication commands — login, status, logout."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import click

from splunkctl import config as cfg_mod
from splunkctl import output
from splunkctl.auth.adapters import ExtractError, get_adapter
from splunkctl.auth.broker import (
    BrokerError,
    browser_available,
    install_hint,
    run_login,
)
from splunkctl.auth.session import (
    SessionError,
    SessionRecord,
    Target,
    delete,
    load,
    resolve_target,
    save,
)


def _config_path(ctx: click.Context) -> Path | None:
    cfg = (ctx.obj or {}).get("config")
    return Path(cfg) if cfg else None


def _auth_mode(
    config_path: Path | None, profile: str | None, target: Target
) -> str | None:
    if target == "siem":
        return cfg_mod.load(config_path, profile=profile).get("auth_mode")
    return cfg_mod.resolve_soar(config_path, profile=profile).get("auth_mode")


@click.group("auth")
def auth_group() -> None:
    """Browser SAML login, session status, and logout for SIEM and SOAR."""


@auth_group.command("login")
@click.option("--target", required=True, type=click.Choice(["siem", "soar"]))
@click.pass_context
def login(ctx: click.Context, target: str) -> None:
    """Complete SAML/MFA in a browser and store a validated product session."""
    obj: dict[str, Any] = ctx.obj or {}
    config_path = _config_path(ctx)
    profile = obj.get("profile")
    timeout = int(obj.get("timeout", 30))
    tgt = cast(Target, target)

    ta = resolve_target(config_path, profile, tgt, timeout=timeout)

    mode = _auth_mode(config_path, profile, tgt)
    if mode in ("token", "password"):
        output.error(
            f"{target} is configured for {mode} authentication, not browser "
            "login. Run 'splunkctl config init' to detect SAML first.",
            kind="usage",
        )
        ctx.exit(1)

    if not browser_available():
        output.error(install_hint(), kind="usage")
        ctx.exit(1)

    adapter = get_adapter(tgt)
    try:
        cookies = run_login(
            login_url=ta.login_url,
            expected_origin=ta.web_url,
            verify=ta.verify,
            timeout=timeout,
        )
        values = adapter.extract(cookies)
        if (
            adapter.validate(
                values, api_base=ta.api_base, verify=ta.verify, timeout=timeout
            )
            != "valid"
        ):
            output.error(
                f"{target} login finished but the product session was rejected.",
                kind="auth",
            )
            ctx.exit(1)
    except (ExtractError, BrokerError, SessionError) as exc:
        output.error(str(exc), kind=getattr(exc, "kind", "auth"))
        ctx.exit(1)
        raise SystemExit(1) from None  # unreachable; ctx.exit raises

    now = time.time()
    record = SessionRecord(
        target=tgt,
        profile=ta.profile,
        origin=ta.web_url,
        values=values,
        acquired_at=now,
        last_validated_at=now,
    )
    save(ta.profile, record)
    output.info(f"{target} session stored (profile '{ta.profile}').")


@auth_group.command("status")
@click.option("--target", type=click.Choice(["siem", "soar", "both"]), default=None)
@click.pass_context
def status(ctx: click.Context, target: str | None) -> None:
    """Report browser-session status: missing, valid, expired, or unreachable."""
    obj: dict[str, Any] = ctx.obj or {}
    config_path = _config_path(ctx)
    profile = obj.get("profile")
    timeout = int(obj.get("timeout", 30))

    targets: list[Target]
    if target in (None, "both"):
        targets = [
            t
            for t in ("siem", "soar")
            if _auth_mode(config_path, profile, t) == "browser"
        ]
    else:
        targets = [cast(Target, target)]

    rows: list[dict[str, Any]] = []
    for tgt in targets:
        try:
            ta = resolve_target(config_path, profile, tgt, timeout=timeout)
        except SessionError:
            continue
        rec = load(ta.profile, tgt, expected_origin=ta.web_url)
        if rec is None:
            rows.append({"target": tgt, "status": "missing"})
            continue
        rows.append(
            {
                "target": tgt,
                "status": get_adapter(tgt).validate(
                    rec.values,
                    api_base=ta.api_base,
                    verify=ta.verify,
                    timeout=ta.timeout,
                ),
            }
        )
    output.render(ctx, rows, empty="No browser-authenticated targets configured.")


@auth_group.command("logout")
@click.option("--target", type=click.Choice(["siem", "soar", "both"]), default=None)
@click.pass_context
def logout(ctx: click.Context, target: str | None) -> None:
    """Best-effort remote logout, then guaranteed local session removal."""
    obj: dict[str, Any] = ctx.obj or {}
    config_path = _config_path(ctx)
    profile = obj.get("profile")
    timeout = int(obj.get("timeout", 30))

    targets: list[Target]
    if target in (None, "both"):
        targets = [
            t
            for t in ("siem", "soar")
            if _auth_mode(config_path, profile, t) == "browser"
        ]
    else:
        targets = [cast(Target, target)]

    failed = False
    for tgt in targets:
        try:
            ta = resolve_target(config_path, profile, tgt, timeout=timeout)
        except SessionError:
            continue
        rec = load(ta.profile, tgt, expected_origin=ta.web_url)
        if rec is not None:
            try:
                get_adapter(tgt).logout(
                    rec.values, web_url=ta.web_url, verify=ta.verify, timeout=ta.timeout
                )
            except Exception:
                output.warning(f"{tgt} remote logout failed; clearing local session.")
        try:
            delete(ta.profile, tgt)
        except SessionError as exc:
            output.error(exc.message, kind=exc.kind)
            failed = True
    if failed:
        ctx.exit(1)
    output.info("Logout complete.")
