"""SOAR platform reads — test, info, health, license."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import errors as err_mod
from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client


@click.command("test")
@click.pass_context
def test(ctx: click.Context) -> None:
    """Verify connectivity and auth against the SOAR instance."""
    client = get_soar_client(ctx)
    try:
        ver = client.get("version")
    except Exception as exc:
        classified = err_mod.classify(exc)
        if classified is not None:
            output.error(
                classified.message,
                kind=classified.kind,
                http_status=classified.http_status,
            )
        else:
            output.error(str(exc))
        ctx.exit(1)
        return
    version = ver.get("version", "unknown")
    output.render(ctx, {"status": "ok", "version": version})


@click.command("info")
@click.pass_context
def info(ctx: click.Context) -> None:
    """Show SOAR version and system info."""
    client = get_soar_client(ctx)
    ver = client.get("version")
    sys_info = client.get("system_info")

    row: dict[str, Any] = {"version": ver.get("version", "unknown")}
    # Merge all system_info fields (keys vary across SOAR versions).
    if isinstance(sys_info, dict):
        for key, val in sys_info.items():
            if key not in row and val is not None:
                row[key] = val
    output.render(ctx, row)


@click.command("health")
@click.pass_context
def health(ctx: click.Context) -> None:
    """Show SOAR daemon health, standby, and cluster status."""
    client = get_soar_client(ctx)
    rows: list[dict[str, Any]] = []

    # Daemon health from /rest/health.
    health_data = client.get("health")
    if isinstance(health_data, dict):
        # Preferred: status dict maps daemon -> state string.
        status_map = health_data.get("status", {})
        services = health_data.get("services", {})
        if isinstance(status_map, dict) and status_map:
            for daemon, state in status_map.items():
                time_val = ""
                svc_entries = services.get(daemon, [])
                if isinstance(svc_entries, list) and svc_entries:
                    time_val = svc_entries[-1].get("time", "")
                rows.append(
                    {
                        "type": "daemon",
                        "name": daemon,
                        "status": state,
                        "time": time_val,
                    }
                )
        # Fallback: iterate services if status dict is absent.
        elif isinstance(services, dict):
            for daemon, entries in services.items():
                if not isinstance(entries, list) or not entries:
                    continue
                latest = entries[-1]
                rows.append(
                    {
                        "type": "daemon",
                        "name": daemon,
                        "status": "running" if latest.get("pid") else "unknown",
                        "time": latest.get("time", ""),
                    }
                )
        # Flat fallback for older shapes.
        else:
            for key, val in health_data.items():
                if isinstance(val, list) and val:
                    latest = val[-1]
                    rows.append(
                        {
                            "type": "daemon",
                            "name": key,
                            "status": latest.get("state", "unknown"),
                            "time": latest.get("time", ""),
                        }
                    )

    # Warm standby — graceful empty on error.
    try:
        standby = client.get("warm_standby")
        status = "unknown"
        if isinstance(standby, dict):
            status = str(standby.get("status", standby.get("warm_standby", "unknown")))
        rows.append({"type": "warm_standby", "name": "warm_standby", "status": status})
    except Exception:
        rows.append(
            {"type": "warm_standby", "name": "warm_standby", "status": "unavailable"}
        )

    # Cluster node — graceful empty on error (lab is unclustered).
    try:
        cluster = client.get("cluster_node")
        if isinstance(cluster, dict):
            data = cluster.get("data", [])
            if data:
                for node in data:
                    rows.append(
                        {
                            "type": "cluster_node",
                            "name": node.get("name", ""),
                            "status": node.get("status", ""),
                        }
                    )
            else:
                rows.append(
                    {
                        "type": "cluster_node",
                        "name": "cluster",
                        "status": "unclustered",
                    }
                )
    except Exception:
        rows.append(
            {"type": "cluster_node", "name": "cluster", "status": "unclustered"}
        )

    output.render(ctx, rows, empty="No health data available.")


@click.command("license")
@click.pass_context
def license_cmd(ctx: click.Context) -> None:
    """Show SOAR license info — type, action quota, usage."""
    client = get_soar_client(ctx)
    data = client.get("license")

    row: dict[str, Any] = {}
    if isinstance(data, dict):
        # Top-level fields.
        if "status" in data:
            row["license_type"] = data["status"]
        # license_info sub-dict (e.g. maximum_actions_per_day).
        info_block = data.get("license_info", {})
        if isinstance(info_block, dict):
            max_actions = info_block.get("maximum_actions_per_day")
            if max_actions is not None:
                row["max_allowed_actions_per_day"] = max_actions
        # current_usage sub-dict.
        usage = data.get("current_usage", {})
        if isinstance(usage, dict):
            for key in (
                "recent_app_run_count",
                "recent_playbook_run_count",
                "recent_debug_run_count",
            ):
                val = usage.get(key)
                if val is not None:
                    row[key] = val
        # Legacy flat keys (older SOAR versions).
        for key in (
            "license_type",
            "max_allowed_actions_per_day",
            "valid_until",
            "actions_used_today",
        ):
            if key not in row:
                val = data.get(key)
                if val is not None:
                    row[key] = val

    output.render(ctx, row, empty="No license data available.")
