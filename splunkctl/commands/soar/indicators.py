"""SOAR indicators & evidence — IOC pivots and evidence management."""

from __future__ import annotations

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARClient, SOARError

# Indicator types accepted by the --type filter.
_INDICATOR_TYPES: list[str] = [
    "ip",
    "domain",
    "hash",
    "url",
    "email",
    "file",
    "process",
    "vault_id",
]

_FEATURE_FLAG_NAME = "use_indicators"
_FLAG_OFF_MSG = (
    "Indicators feature is disabled on this SOAR instance. "
    "Enable it in Administration > Product Settings > Feature Toggles, "
    f"or POST /rest/feature_flag with name='{_FEATURE_FLAG_NAME}' "
    "and value=true."
)


# -- Feature detection -------------------------------------------------------


def _check_indicator_flag(ctx: click.Context, client: SOARClient) -> bool:
    """Return True if the indicators feature flag is enabled.

    On failure (flag off or unreachable), prints an actionable message
    to stderr and returns False.
    """
    try:
        result = client.get(
            "feature_flag",
            params={"_filter_name": f'"{_FEATURE_FLAG_NAME}"'},
        )
    except SOARError:
        # Cannot reach feature_flag endpoint — assume off.
        output.error(_FLAG_OFF_MSG, kind="feature")
        ctx.exit(1)
        return False

    data: list[dict[str, Any]] = []
    if isinstance(result, dict):
        data = result.get("data", [])

    for flag in data:
        if isinstance(flag, dict) and flag.get("name") == _FEATURE_FLAG_NAME:
            if flag.get("value") is True or str(flag.get("value")).lower() == "true":
                return True

    output.error(_FLAG_OFF_MSG, kind="feature")
    ctx.exit(1)
    return False


# -- Indicator commands -------------------------------------------------------


@click.group("indicators")
def indicators_group() -> None:
    """IOC indicators and evidence management."""


@indicators_group.command("list")
@click.option(
    "--type",
    "indicator_type",
    default=None,
    type=click.Choice(_INDICATOR_TYPES),
    help="Filter by indicator type.",
)
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Page size.")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    indicator_type: str | None,
    limit: int | None,
) -> None:
    """List indicators (requires indicators feature flag)."""
    client = get_soar_client(ctx)
    if not _check_indicator_flag(ctx, client):
        return

    params: dict[str, Any] = {}
    if indicator_type is not None:
        params["_filter_type"] = f'"{indicator_type}"'
    if limit is not None:
        params["page_size"] = limit

    try:
        result = client.get("indicator", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No indicators found.")


@indicators_group.command("get")
@click.argument("value")
@click.pass_context
def get_cmd(ctx: click.Context, *, value: str) -> None:
    """Look up an indicator by value (indicator_by_value)."""
    client = get_soar_client(ctx)
    if not _check_indicator_flag(ctx, client):
        return

    try:
        result = client.get(
            "indicator_by_value",
            params={"indicator_value": value},
        )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict) and "data" in result:
        data = result["data"]
        if isinstance(data, list):
            output.render(ctx, data, empty=f"No indicator found for '{value}'.")
        else:
            output.render(ctx, data)
    else:
        output.render(ctx, result if isinstance(result, dict) else {})


@indicators_group.command("pivot")
@click.argument("value")
@click.pass_context
def pivot_cmd(ctx: click.Context, *, value: str) -> None:
    """Show containers where an IOC has been seen (common containers)."""
    client = get_soar_client(ctx)
    if not _check_indicator_flag(ctx, client):
        return

    try:
        result = client.get(
            "indicator_common_container",
            params={"indicator_value": value},
        )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty=f"No containers found for indicator '{value}'.")


@indicators_group.command("stats")
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    """Indicator statistics overview."""
    client = get_soar_client(ctx)
    if not _check_indicator_flag(ctx, client):
        return

    rows: list[dict[str, Any]] = []
    for endpoint in ("indicator_stats_type", "indicator_stats_severity"):
        try:
            result = client.get(endpoint)
        except SOARError:
            result = {"source": endpoint, "error": "unavailable"}
        if isinstance(result, dict):
            data = result.get("data", [])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        rows.append({"source": endpoint, **item})
            else:
                rows.append({"source": endpoint, **result})
        else:
            rows.append({"source": endpoint, "data": result})

    output.render(ctx, rows, empty="No indicator stats available.")


# -- Evidence commands --------------------------------------------------------


@click.group("evidence")
def evidence_group() -> None:
    """Evidence management for SOAR containers."""


@evidence_group.command("list")
@click.option(
    "--container",
    "container_id",
    required=True,
    type=int,
    help="Container ID to list evidence for.",
)
@click.pass_context
def evidence_list_cmd(ctx: click.Context, *, container_id: int) -> None:
    """List evidence items for a container."""
    client = get_soar_client(ctx)

    try:
        result = client.get(
            "evidence",
            params={"_filter_container": container_id},
        )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty=f"No evidence found for container {container_id}.")


@evidence_group.command("add")
@guard.guarded
@click.argument("container_id", type=int)
@click.option(
    "--object",
    "object_type",
    required=True,
    type=click.Choice(["artifact", "note", "action_run"]),
    help="Type of object to add as evidence.",
)
@click.option(
    "--id",
    "object_id",
    required=True,
    type=int,
    help="ID of the object to add.",
)
@click.pass_context
def evidence_add_cmd(
    ctx: click.Context,
    container_id: int,
    *,
    object_type: str,
    object_id: int,
) -> None:
    """Add an object as evidence to a container."""
    body: dict[str, Any] = {
        "container_id": container_id,
        "object_type": object_type,
        "object_id": object_id,
    }
    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Add {object_type} {object_id} as evidence to container {container_id}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("evidence", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Evidence added: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


@evidence_group.command("remove")
@guard.guarded
@click.argument("evidence_id", type=int)
@click.pass_context
def evidence_remove_cmd(ctx: click.Context, evidence_id: int) -> None:
    """Remove an evidence item by ID."""
    if not guard.soar_check(ctx, f"Remove evidence {evidence_id}"):
        return

    client = get_soar_client(ctx)
    try:
        client.delete(f"evidence/{evidence_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Evidence {evidence_id} removed.")
