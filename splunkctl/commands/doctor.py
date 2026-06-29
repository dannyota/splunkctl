"""Doctor command — diagnose connection, auth, and permissions."""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Any

import click

from splunkctl.client import get_client

_KEY_CAPABILITIES = (
    "search",
    "admin_all_objects",
    "edit_user",
    "edit_roles",
    "edit_tcp",
    "edit_monitor",
    "list_inputs",
    "rest_apps_management",
    "change_own_password",
)


def _check(
    label: str,
    passed: bool,
    detail: str = "",
    *,
    warn: bool = False,
) -> dict[str, str]:
    if passed:
        status = "OK"
    elif warn:
        status = "WARN"
    else:
        status = "FAIL"
    click.echo(f"  {'PASS' if passed else status:4s}  {label}", err=True)
    if detail:
        click.echo(f"        {detail}", err=True)
    return {"check": label, "status": status, "detail": detail}


@click.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Check connection, auth, server health, and user permissions."""
    results: list[dict[str, str]] = []
    click.echo("splunkctl doctor", err=True)
    click.echo("", err=True)

    # --- 1. REST connection ---
    click.echo("[Connection]", err=True)
    client = get_client(ctx)
    try:
        svc = client.service
        results.append(_check("REST API reachable", True))
    except Exception as exc:
        results.append(_check("REST API reachable", False, str(exc)))
        _finish(ctx, results)
        return

    # --- 2. Auth ---
    click.echo("[Auth]", err=True)
    info: dict[str, Any] = dict(svc.info)
    results.append(
        _check(
            "Authenticated",
            True,
            f"user={svc.username}",
        )
    )

    # --- 3. Server info ---
    click.echo("[Server]", err=True)
    version = info.get("version", "?")
    os_name = info.get("os_name", "?")
    results.append(_check("Splunk version", True, version))
    results.append(_check("OS", True, f"{os_name} {info.get('os_version', '')}"))

    mode = info.get("mode", "?")
    results.append(_check("Mode", True, mode))

    lic_state = info.get("licenseState", "?")
    is_trial = str(info.get("isTrial", "0")) == "1"
    lic_ok = lic_state == "OK"
    lic_detail = lic_state
    if is_trial:
        lic_detail += " (trial)"
    results.append(_check("License", lic_ok, lic_detail, warn=not lic_ok))

    # --- 4. Health ---
    click.echo("[Health]", err=True)
    try:
        resp = svc.get("/services/server/health/splunkd", output_mode="json")
        health_data = json.loads(resp.body.read())
        health = health_data["entry"][0]["content"].get("health", "unknown")
        health_ok = health == "green"
        results.append(
            _check(
                "Splunkd health",
                health_ok,
                health,
                warn=not health_ok,
            )
        )
    except Exception:
        results.append(_check("Splunkd health", False, "could not query"))

    msgs = svc.messages.list()
    errors = [m for m in msgs if m.content.get("severity") == "error"]
    warns = [m for m in msgs if m.content.get("severity") == "warn"]
    if errors:
        names = ", ".join(m.name for m in errors[:3])
        if len(errors) > 3:
            names += f" (+{len(errors) - 3} more)"
        results.append(_check("System messages", False, names, warn=True))
    elif warns:
        results.append(
            _check(
                "System messages",
                True,
                f"{len(warns)} warning(s)",
            )
        )
    else:
        results.append(_check("System messages", True, "no errors"))

    # --- 5. User permissions ---
    click.echo("[Permissions]", err=True)
    try:
        user = svc.users[svc.username]
        uc: dict[str, Any] = user.content
        roles = uc.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        results.append(_check("Roles", True, ", ".join(roles)))

        caps = uc.get("capabilities", [])
        if isinstance(caps, str):
            caps = [caps]
        cap_set = set(caps)

        for cap in _KEY_CAPABILITIES:
            results.append(_check(f"cap:{cap}", cap in cap_set))
    except Exception as exc:
        results.append(_check("User lookup", False, str(exc)))

    # --- 6. Web UI ---
    click.echo("[Web UI]", err=True)
    try:
        web_conf = svc.confs["web"]["settings"]
        web_port = int(web_conf["httpport"])
        web_ssl = str(web_conf.content.get("enableSplunkWebSSL", "0")) == "1"
        scheme = "https" if web_ssl else "http"
        web_url = f"{scheme}://{svc.host}:{web_port}"

        ctx_ssl = ssl.create_default_context()
        ctx_ssl.check_hostname = False
        ctx_ssl.verify_mode = ssl.CERT_NONE  # noqa: S501
        handler = urllib.request.HTTPSHandler(context=ctx_ssl)
        opener = urllib.request.build_opener(handler)
        resp = opener.open(  # noqa: S310
            f"{web_url}/en-US/account/login",
            timeout=5,
        )
        results.append(
            _check(
                "Web UI reachable",
                resp.status == 200,
                f"{web_url} (port {web_port})",
            )
        )
    except Exception as exc:
        results.append(
            _check(
                "Web UI reachable",
                False,
                f"port {web_port}: {exc}" if "web_port" in dir() else str(exc),
                warn=True,
            )
        )

    _finish(ctx, results)


def _finish(ctx: click.Context, results: list[dict[str, str]]) -> None:
    click.echo("", err=True)
    fails = sum(1 for r in results if r["status"] == "FAIL")
    warns = sum(1 for r in results if r["status"] == "WARN")
    total = len(results)
    passed = total - fails - warns
    click.echo(
        f"  {passed}/{total} passed, {warns} warnings, {fails} failures",
        err=True,
    )

    obj: dict[str, Any] = ctx.ensure_object(dict)
    fmt = obj.get("format", "")
    if fmt == "json" or obj.get("json"):
        click.echo(json.dumps(results, indent=2))

    if fails:
        ctx.exit(1)
