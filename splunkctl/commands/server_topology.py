"""Server topology & health commands (cluster, SHC, deployment, peers)."""

import json
from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client


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


def _rest_get(svc: Any, path: str, **params: Any) -> dict[str, Any]:
    """GET a REST path and parse JSON. Thin wrapper for topology reads."""
    resp = svc.get(path, output_mode="json", **params)
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


@click.command("cluster")
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


@click.command("shcluster")
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


@click.command("deployment")
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
            output.render(ctx, {"status": "disabled", "detail": _disabled_detail(exc)})
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


# ---------------------------------------------------------------------------
# splunkd health report & distributed-search peers
# ---------------------------------------------------------------------------


def _reason_text(node: dict[str, Any]) -> str:
    """Join a health node's nested reason strings, if any."""
    reasons = node.get("reasons")
    if not isinstance(reasons, dict):
        return ""
    texts: list[str] = []
    for bucket in reasons.values():
        if not isinstance(bucket, dict):
            continue
        for item in bucket.values():
            if isinstance(item, dict) and item.get("reason"):
                texts.append(str(item["reason"]))
    return "; ".join(texts)


def _walk_health(node: dict[str, Any], label: str, rows: list[dict[str, Any]]) -> None:
    """Flatten the health feature tree into one row per component."""
    rows.append(
        {
            "component": label,
            "health": node.get("health", ""),
            "reasons": _reason_text(node),
        }
    )
    features = node.get("features") or {}
    for child_name, child in sorted(features.items()):
        if not isinstance(child, dict):
            continue
        child_label = child_name if label == "splunkd" else f"{label} / {child_name}"
        _walk_health(child, child_label, rows)


@click.command("health")
@click.pass_context
def health_report(ctx: click.Context) -> None:
    """Component-level splunkd health report (scheduler, disk, KV store...).

    Flattens the health-report feature tree into one row per component;
    nested feature names join with " / ". This command reports — it does
    not gate: red components still exit 0.
    """
    client = get_client(ctx)
    body = _rest_get(client.service, "/services/server/health/splunkd/details")
    entries: list[dict[str, Any]] = body.get("entry", [])
    rows: list[dict[str, Any]] = []
    if entries:
        _walk_health(entries[0].get("content", {}), "splunkd", rows)
    output.render(ctx, rows, empty="No health report available.")


@click.command("search-peers")
@click.pass_context
def search_peers(ctx: click.Context) -> None:
    """Distributed-search peers — status, replication, version.

    Lists every search peer this instance fans searches out to. Empty on
    a standalone instance (exit 0).
    """
    client = get_client(ctx)
    try:
        body = _rest_get(client.service, "/services/search/distributed/peers", count=-1)
    except Exception as exc:
        if _is_not_enabled(exc):
            output.render(ctx, {"status": "disabled", "detail": _disabled_detail(exc)})
            return
        raise

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "peer": c.get("peerName", entry.get("name", "")),
                "status": c.get("status", ""),
                "replication_status": c.get("replicationStatus", ""),
                "version": c.get("version", ""),
            }
        )
    output.render(ctx, rows, empty="No search peers (standalone instance).")
