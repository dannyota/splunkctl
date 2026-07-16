"""Workload management reads — pools, rules, status (Splunk 8.1+)."""

import json
from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client


def _is_not_available(exc: Exception) -> bool:
    """True when the endpoint signals workload management is not available.

    Splunk returns 404 when the workload management feature is not
    enabled or the version is too old (pre-8.1). HTTP 503 with "not
    enabled" also qualifies. Any other status is a genuine error.
    """
    if type(exc).__name__ != "HTTPError":
        return False
    status: int | None = getattr(exc, "status", None)
    if status == 404:
        return True
    if status == 503:
        return "not enabled" in str(exc).lower()
    return False


def _rest_json(svc: Any, path: str, **params: Any) -> dict[str, Any]:
    """GET a REST path and parse JSON."""
    resp = svc.get(path, output_mode="json", **params)
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


@click.group("workloads")
def workloads_group() -> None:
    """Workload management — pools, admission rules, current load (Splunk 8.1+)."""


@workloads_group.command("pools")
@click.pass_context
def workloads_pools(ctx: click.Context) -> None:
    """List workload pools — CPU/memory weights and search types.

    Requires Splunk 8.1+ with workload management enabled. Reports a
    clean not-available status and exits 0 on older or unconfigured
    instances.
    """
    client = get_client(ctx)
    try:
        body = _rest_json(client.service, "/services/workloads/pools", count=-1)
    except Exception as exc:
        if _is_not_available(exc):
            output.render(
                ctx,
                {
                    "status": "not_available",
                    "detail": "Workload management is not enabled or not supported.",
                },
            )
            return
        raise

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name", ""),
                "cpu_weight": c.get("cpu_weight", ""),
                "mem_weight": c.get("mem_weight", ""),
                "default_category": c.get("default_category", ""),
                "category": c.get("category", ""),
            }
        )
    output.render(ctx, rows, empty="No workload pools configured.")


@workloads_group.command("rules")
@click.pass_context
def workloads_rules(ctx: click.Context) -> None:
    """List workload admission rules.

    Shows rule names, predicates, and the workload pool they route
    searches into. Requires Splunk 8.1+ with workload management
    enabled.
    """
    client = get_client(ctx)
    try:
        body = _rest_json(client.service, "/services/workloads/rules", count=-1)
    except Exception as exc:
        if _is_not_available(exc):
            output.render(
                ctx,
                {
                    "status": "not_available",
                    "detail": "Workload management is not enabled or not supported.",
                },
            )
            return
        raise

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name", ""),
                "predicate": c.get("predicate", ""),
                "workload_pool": c.get("workload_pool", ""),
                "action": c.get("action", ""),
                "order": c.get("order", ""),
                "schedule": c.get("schedule", ""),
            }
        )
    output.render(ctx, rows, empty="No workload admission rules configured.")


@workloads_group.command("status")
@click.pass_context
def workloads_status(ctx: click.Context) -> None:
    """Show current workload management status and load.

    Reports whether workload management is enabled and the current
    resource utilization. Requires Splunk 8.1+.
    """
    client = get_client(ctx)
    try:
        body = _rest_json(client.service, "/services/workloads/status", count=-1)
    except Exception as exc:
        if _is_not_available(exc):
            output.render(
                ctx,
                {
                    "status": "not_available",
                    "detail": "Workload management is not enabled or not supported.",
                },
            )
            return
        raise

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.render(
            ctx,
            {"status": "not_available", "detail": "No workload status data."},
        )
        return

    c: dict[str, Any] = entries[0].get("content", {})
    row: dict[str, Any] = {
        "status": c.get("status", c.get("is_enabled", "")),
        "admission_rules_enabled": c.get("admission_rules_enabled", ""),
    }

    # Include pool-level utilisation if the response nests it
    pools: Any = c.get("pools")
    if isinstance(pools, dict):
        pool_rows: list[dict[str, Any]] = []
        for pool_name, pool_data in pools.items():
            if isinstance(pool_data, dict):
                pool_rows.append(
                    {
                        "pool": pool_name,
                        "cpu_usage": pool_data.get("cpu_usage", ""),
                        "mem_usage": pool_data.get("mem_usage", ""),
                        "search_count": pool_data.get("search_count", ""),
                    }
                )
        if pool_rows:
            row["pools"] = pool_rows

    output.render(ctx, row)
