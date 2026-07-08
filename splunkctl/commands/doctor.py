"""Doctor command — diagnose connection, auth, and permissions."""

from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path
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

_HINTS: dict[str, str] = {
    "REST API reachable": ("Check SPLUNK_HOST/SPLUNK_PORT and that Splunk is running."),
    "Authenticated": "Verify SPLUNK_USER/SPLUNK_PASS or SPLUNK_TOKEN.",
    "License": "Run 'splunkctl server license' to inspect license state.",
    "Splunkd health": ("Run 'splunkctl server messages' to see system warnings."),
    "System messages": (
        "Dismiss with 'splunkctl server messages --dismiss NAME --yes'."
    ),
    "Web UI reachable": ("Web UI is optional; lookup-upload and some ops need it."),
    "KV Store": ("Ask your Splunk admin to restart Splunk or check mongod.log."),
    "MCP registered": "Run 'splunkctl mcp install' to register the MCP server.",
}


def _check(
    label: str,
    passed: bool,
    detail: str = "",
    *,
    warn: bool = False,
    hint: str = "",
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
    resolved_hint = hint or _HINTS.get(label, "")
    if not passed and resolved_hint:
        click.echo(f"        hint: {resolved_hint}", err=True)
    entry: dict[str, str] = {
        "check": label,
        "status": status,
        "detail": detail,
    }
    if not passed and resolved_hint:
        entry["hint"] = resolved_hint
    return entry


@click.command("doctor")
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as failures (exit 1).",
)
@click.pass_context
def doctor_cmd(ctx: click.Context, *, strict: bool = False) -> None:
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
        _finish(ctx, results, strict=strict)
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

    # --- 5. KV Store ---
    click.echo("[KV Store]", err=True)
    try:
        resp = svc.get("/services/kvstore/status", output_mode="json")
        kv_data = json.loads(resp.body.read())
        kv_status = kv_data["entry"][0]["content"].get("current", {})
        kv_state = kv_status.get("status", "unknown")
        kv_ok = kv_state == "ready"
        kv_detail = kv_state
        if not kv_ok and kv_state == "failed":
            kv_detail = "failed — restart Splunk or check mongod.log"
        results.append(_check("KV Store", kv_ok, kv_detail, warn=not kv_ok))
    except Exception:
        results.append(_check("KV Store", False, "could not query status", warn=True))

    # --- 6. User permissions ---
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
            hint = f"Grant '{cap}' to your user or role." if cap not in cap_set else ""
            results.append(_check(f"cap:{cap}", cap in cap_set, hint=hint))
    except Exception as exc:
        results.append(_check("User lookup", False, str(exc)))

    # --- 7. Web UI ---
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

    # --- 8. MCP registration ---
    click.echo("[MCP]", err=True)
    _check_mcp_registered(results)

    _finish(ctx, results, strict=strict)


def _check_mcp_registered(results: list[dict[str, str]]) -> None:
    mcp_json = Path.cwd() / ".mcp.json"
    if not mcp_json.exists():
        results.append(
            _check("MCP registered", False, ".mcp.json not found", warn=True)
        )
        return
    try:
        data = json.loads(mcp_json.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        if "splunkctl" in servers:
            results.append(_check("MCP registered", True, ".mcp.json"))
        else:
            results.append(
                _check(
                    "MCP registered",
                    False,
                    "splunkctl entry missing from .mcp.json",
                    warn=True,
                )
            )
    except Exception as exc:
        results.append(_check("MCP registered", False, str(exc)))


def _finish(
    ctx: click.Context,
    results: list[dict[str, str]],
    *,
    strict: bool = False,
) -> None:
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

    if fails or (strict and warns):
        ctx.exit(1)
