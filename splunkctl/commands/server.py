"""Server operations — messages, license, KV store, topology health."""

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _is_not_enabled(exc: Exception) -> bool:
    """True when an HTTPError signals a feature is not enabled (clean exit 0).

    Splunk returns HTTP 503 with a descriptive message when clustering or
    deployment-server features are disabled. Only 503 with "not enabled"
    text qualifies — any other status (401, 404, 500...) is a genuine
    error that should propagate to the F1 classifier.
    """
    if type(exc).__name__ != "HTTPError":
        return False
    status: int | None = getattr(exc, "status", None)
    if status != 503:
        return False
    msg = str(exc).lower()
    return "not enabled" in msg


def _disabled_detail(exc: Exception) -> str:
    """Human-readable message from a feature-disabled HTTPError.

    Splunk's error body is JSON (``{"messages": [{"text": ...}]}``) when
    the request asked for ``output_mode=json``, XML otherwise; ``str(exc)``
    would embed the raw bytes literal for JSON bodies.
    """
    raw = getattr(exc, "body", b"") or b""
    body = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    try:
        msgs = json.loads(body).get("messages", [])
        texts = [m.get("text") for m in msgs if isinstance(m, dict)]
        if any(texts):
            return "; ".join(t for t in texts if t)
    except (json.JSONDecodeError, AttributeError):
        pass
    try:
        from defusedxml.ElementTree import fromstring

        text = fromstring(body).findtext("./messages/msg")
        if text:
            return text
    except Exception:  # noqa: BLE001, S110
        pass
    return str(getattr(exc, "reason", "") or exc)


def _rest_get(svc: Any, path: str) -> dict[str, Any]:
    """GET a REST path and parse JSON. Thin wrapper for topology reads."""
    resp = svc.get(path, output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


@click.group("server")
def server_group() -> None:
    """Server operations — messages, license, KV store, topology health."""


@server_group.command("messages")
@guard.guarded
@click.option("--dismiss", default=None, help="Delete a message by name.")
@click.pass_context
def messages(ctx: click.Context, dismiss: str | None) -> None:
    """List system messages, or dismiss one with --dismiss NAME --yes."""
    client = get_client(ctx)
    svc = client.service

    if dismiss is not None:
        if not guard.check(ctx, f"Dismiss system message '{dismiss}'"):
            return
        try:
            msg = svc.messages[dismiss]
        except KeyError:
            output.error(f"Message '{dismiss}' not found.", kind="not_found")
            ctx.exit(1)
            return
        msg.delete()
        output.info(f"Message '{dismiss}' dismissed.")
        return

    rows: list[dict[str, Any]] = []
    for msg in svc.messages.list():
        c: dict[str, Any] = msg.content
        rows.append(
            {
                "name": msg.name,
                "severity": c.get("severity", ""),
                "message": c.get("message", ""),
                "time_created": c.get("timeCreated_iso", c.get("timeCreated", "")),
            }
        )
    output.render(ctx, rows, empty="No system messages.")


@server_group.command("license")
@click.pass_context
def license_pools(ctx: click.Context) -> None:
    """Show license pool usage."""
    client = get_client(ctx)
    resp = client.service.get("/services/licenser/pools", output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        used = int(c.get("used_bytes", 0))
        quota = int(c.get("effective_quota", 0))
        rows.append(
            {
                "title": entry.get("name", ""),
                "used": _human_bytes(used),
                "quota": _human_bytes(quota),
            }
        )
    output.render(ctx, rows, empty="No license pools found.")


@server_group.command("kvstore")
@click.pass_context
def kvstore_status(ctx: click.Context) -> None:
    """Show KV store status."""
    client = get_client(ctx)
    resp = client.service.get("/services/kvstore/status", output_mode="json")
    body: dict[str, Any] = json.loads(resp.body.read())

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error("No KV store status available.")
        ctx.exit(1)
        return

    c: dict[str, Any] = entries[0].get("content", {})
    current: dict[str, Any] = c.get("current") or {}
    status_raw = current.get("status")
    status = "unknown" if not status_raw else str(status_raw).lower()
    row: dict[str, Any] = {
        "status": status,
        "port": current.get("port", ""),
        "version": current.get("version", ""),
        "storage_engine": current.get("storageEngine", ""),
        "db_path": current.get("dbPath", ""),
    }
    output.render(ctx, row)


# ---------------------------------------------------------------------------
# Topology health (read-only)
# ---------------------------------------------------------------------------


@server_group.command("cluster")
@click.pass_context
def cluster_health(ctx: click.Context) -> None:
    """Indexer cluster health — mode, peers, SF/RF status.

    On a non-clustered instance, reports mode=disabled and exits 0.
    Prefers the ``cluster/manager`` endpoint (Splunk 9+); falls back
    to ``cluster/master`` on older versions.
    """
    client = get_client(ctx)
    svc = client.service

    prefix = "cluster/manager"
    try:
        info_body = _rest_get(svc, f"/services/{prefix}/info")
    except Exception as exc:
        if _is_not_enabled(exc):
            output.render(ctx, {"mode": "disabled", "detail": _disabled_detail(exc)})
            return
        # 404 -> try legacy master prefix
        if type(exc).__name__ == "HTTPError" and getattr(exc, "status", 0) == 404:
            prefix = "cluster/master"
            try:
                info_body = _rest_get(svc, f"/services/{prefix}/info")
            except Exception as inner:
                if _is_not_enabled(inner):
                    output.render(
                        ctx,
                        {"mode": "disabled", "detail": _disabled_detail(inner)},
                    )
                    return
                raise
        else:
            raise

    entries: list[dict[str, Any]] = info_body.get("entry", [])
    if not entries:
        output.render(ctx, {"mode": "disabled", "detail": "no cluster info"})
        return

    c: dict[str, Any] = entries[0].get("content", {})
    rows: list[dict[str, Any]] = [
        {
            "mode": c.get("mode", "unknown"),
            "label": c.get("label", ""),
            "replication_factor_met": c.get("replication_factor_met"),
            "search_factor_met": c.get("search_factor_met"),
            "rolling_restart": c.get("rolling_restart_flag", False),
            "maintenance_mode": c.get("maintenance_mode", False),
        }
    ]

    # Fetch peers
    try:
        peers_body = _rest_get(svc, f"/services/{prefix}/peers")
        for entry in peers_body.get("entry", []):
            pc: dict[str, Any] = entry.get("content", {})
            rows.append(
                {
                    "label": pc.get("label", entry.get("name", "")),
                    "status": pc.get("status", ""),
                    "site": pc.get("site", ""),
                    "search_state": pc.get("search_state", ""),
                    "replication_count": pc.get("replication_count", 0),
                    "bucket_count": pc.get("bucket_count", 0),
                }
            )
    except Exception as exc:
        if not _is_not_enabled(exc):
            raise

    output.render(ctx, rows, empty="No cluster info available.")


@server_group.command("shcluster")
@click.pass_context
def shcluster_health(ctx: click.Context) -> None:
    """Search head cluster health — captain, members, replication.

    On a non-SHC instance, reports mode=disabled and exits 0.
    """
    client = get_client(ctx)
    svc = client.service

    try:
        body = _rest_get(svc, "/services/shcluster/status")
    except Exception as exc:
        if _is_not_enabled(exc):
            output.render(ctx, {"mode": "disabled", "detail": _disabled_detail(exc)})
            return
        raise

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.render(ctx, {"mode": "disabled", "detail": "no SHC status"})
        return

    c: dict[str, Any] = entries[0].get("content", {})
    captain: dict[str, Any] = c.get("captain", {})
    rows: list[dict[str, Any]] = [
        {
            "captain": captain.get("label", ""),
            "captain_id": captain.get("id", ""),
            "dynamic_captain": captain.get("dynamic_captain"),
            "elected_captain": captain.get("elected_captain", ""),
        }
    ]

    peers: dict[str, Any] = c.get("peers", {})
    for _guid, member in peers.items():
        rows.append(
            {
                "label": member.get("label", ""),
                "status": member.get("status", ""),
                "site": member.get("site", ""),
                "out_of_sync": member.get("out_of_sync_node", False),
            }
        )

    output.render(ctx, rows, empty="No SHC status available.")


@server_group.command("deployment")
@click.pass_context
def deployment_health(ctx: click.Context) -> None:
    """Deployment server clients — count, last check-in.

    If no clients are registered (or the deployment server feature is
    not enabled), reports a clean status and exits 0.
    """
    client = get_client(ctx)
    svc = client.service

    try:
        body = _rest_get(svc, "/services/deployment/server/clients")
    except Exception as exc:
        if _is_not_enabled(exc):
            output.render(
                ctx, {"status": "disabled", "detail": _disabled_detail(exc)}
            )
            return
        raise

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.render(
            ctx,
            {"status": "no_clients", "total": 0},
            empty="No deployment clients.",
        )
        return

    rows: list[dict[str, Any]] = []
    for entry in entries:
        ec: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "client": ec.get("clientName", entry.get("name", "")),
                "hostname": ec.get("hostname", ""),
                "ip": ec.get("ip", ""),
                "last_phone_home": ec.get("phoneHomeTime", ""),
                "phone_home_interval": ec.get("averagePhoneHomeInterval", ""),
            }
        )

    output.render(ctx, rows)
