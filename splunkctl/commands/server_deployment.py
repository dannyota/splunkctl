"""Deployment-server serverclass management — list, get, reload."""

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_SC_PATH = "/services/deployment/server/serverclasses"


def _is_ds_disabled(exc: Exception) -> bool:
    """True when the deployment server feature is not enabled (503)."""
    if type(exc).__name__ != "HTTPError":
        return False
    status: int | None = getattr(exc, "status", None)
    if status != 503:
        return False
    return "not enabled" in str(exc).lower()


def _rest_json(svc: Any, path: str, **params: Any) -> dict[str, Any]:
    """GET a REST path and parse JSON."""
    resp = svc.get(path, output_mode="json", **params)
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


def _parse_serverclass(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten a serverclass entry into a display row."""
    c: dict[str, Any] = entry.get("content", {})

    # whitelist / blacklist may be a list or a single string
    def _as_list(val: Any) -> list[str]:
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val:
            return [val]
        return []

    whitelist = _as_list(c.get("whitelist.0", c.get("whitelist", [])))
    blacklist = _as_list(c.get("blacklist.0", c.get("blacklist", [])))

    return {
        "name": entry.get("name", ""),
        "restartSplunkd": c.get("restartSplunkd", False),
        "stateOnClient": c.get("stateOnClient", ""),
        "whitelist": whitelist,
        "blacklist": blacklist,
    }


def _parse_serverclass_detail(entry: dict[str, Any]) -> dict[str, Any]:
    """Full detail view of a serverclass including apps."""
    row = _parse_serverclass(entry)
    c: dict[str, Any] = entry.get("content", {})
    row["repositoryLocation"] = c.get("repositoryLocation", "")
    row["targetRepositoryLocation"] = c.get("targetRepositoryLocation", "")
    row["endpoint"] = c.get("endpoint", "")
    row["filterType"] = c.get("filterType", "")
    return row


@click.group("serverclasses")
def serverclasses_group() -> None:
    """Deployment-server serverclass management."""


@serverclasses_group.command("list")
@click.pass_context
def list_serverclasses(ctx: click.Context) -> None:
    """List deployment-server serverclasses.

    Shows name, restartSplunkd, stateOnClient, and client
    whitelist/blacklist filters. Requires the deployment server to be
    enabled; reports a clean disabled status and exits 0 if not.
    """
    client = get_client(ctx)
    try:
        body = _rest_json(client.service, _SC_PATH, count=-1)
    except Exception as exc:
        if _is_ds_disabled(exc):
            output.render(
                ctx,
                {"status": "disabled", "detail": "Deployment server is not enabled."},
            )
            return
        raise

    rows = [_parse_serverclass(e) for e in body.get("entry", [])]
    output.render(ctx, rows, empty="No serverclasses found.")


@serverclasses_group.command("get")
@click.argument("name")
@click.pass_context
def get_serverclass(ctx: click.Context, name: str) -> None:
    """Show detail for a single serverclass, including app config."""
    client = get_client(ctx)
    svc = client.service

    try:
        body = _rest_json(svc, f"{_SC_PATH}/{name}")
    except Exception as exc:
        if _is_ds_disabled(exc):
            output.render(
                ctx,
                {"status": "disabled", "detail": "Deployment server is not enabled."},
            )
            return
        if type(exc).__name__ == "HTTPError" and getattr(exc, "status", 0) == 404:
            output.error(f"Serverclass '{name}' not found.", kind="not_found")
            ctx.exit(1)
            return
        raise

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error(f"Serverclass '{name}' not found.", kind="not_found")
        ctx.exit(1)
        return

    row = _parse_serverclass_detail(entries[0])

    # Fetch apps for this serverclass
    try:
        apps_body = _rest_json(svc, f"{_SC_PATH}/{name}/apps", count=-1)
        apps: list[dict[str, Any]] = []
        for app_entry in apps_body.get("entry", []):
            ac: dict[str, Any] = app_entry.get("content", {})
            apps.append(
                {
                    "app": app_entry.get("name", ""),
                    "restartSplunkd": ac.get("restartSplunkd", False),
                    "stateOnClient": ac.get("stateOnClient", ""),
                }
            )
        row["apps"] = apps
    except Exception:  # noqa: BLE001
        # Apps sub-endpoint may not exist; best-effort
        row["apps"] = []

    output.render(ctx, row)


@serverclasses_group.command("reload")
@guard.guarded
@click.argument("name")
@click.pass_context
def reload_serverclass(ctx: click.Context, name: str) -> None:
    """Reload a serverclass to push updated apps to clients.

    Guarded: pass --yes to apply.
    """
    if not guard.check(ctx, f"Reload serverclass '{name}'"):
        return

    client = get_client(ctx)
    svc = client.service

    try:
        svc.post(f"{_SC_PATH}/{name}/reload", output_mode="json")
    except Exception as exc:
        if _is_ds_disabled(exc):
            output.error("Deployment server is not enabled.", kind="error")
            ctx.exit(1)
            return
        if type(exc).__name__ == "HTTPError" and getattr(exc, "status", 0) == 404:
            output.error(f"Serverclass '{name}' not found.", kind="not_found")
            ctx.exit(1)
            return
        raise

    output.info(f"Serverclass '{name}' reloaded.")
