"""SOAR container reads — list with filters, get with sub-views."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARClient, SOARError

# Sub-view flags and their API path suffixes.
_SUB_VIEWS: dict[str, str] = {
    "artifacts": "artifacts",
    "notes": "notes",
    "comments": "comments",
    "audit": "audit",
    "activity": "activity_feed",
    "playbook_runs": "playbook_runs",
    "phases": "phases",
}

# SOAR container_type values: CLI "event" -> API "default".
_TYPE_MAP: dict[str, str] = {
    "event": "default",
    "case": "case",
}


@click.group("containers")
def containers_group() -> None:
    """Container reads — list, get, sub-views."""


@containers_group.command("list")
@click.option("--label", default=None, help="Filter by container label.")
@click.option(
    "--status",
    default=None,
    help="Filter by status name (resolved via container_status).",
)
@click.option("--severity", default=None, help="Filter by severity name.")
@click.option("--owner", default=None, help="Filter by owner username.")
@click.option(
    "--since",
    default=None,
    help="Containers created after this timestamp.",
)
@click.option(
    "--type",
    "container_type",
    default=None,
    type=click.Choice(["event", "case"]),
    help="Filter by type: event (default) or case.",
)
@click.option(
    "--filter",
    "raw_filter",
    default=None,
    help='Raw Django filter (key=value, e.g. _filter_name__icontains="dns").',
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Page size.",
)
@click.option(
    "--offset",
    default=None,
    type=int,
    help="Row offset; requires --limit and must be a multiple of it.",
)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    label: str | None,
    status: str | None,
    severity: str | None,
    owner: str | None,
    since: str | None,
    container_type: str | None,
    raw_filter: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    """List containers with optional filters."""
    if offset is not None and limit is None:
        output.error("--offset requires --limit", kind="usage")
        ctx.exit(1)
        return
    if offset is not None and limit is not None and offset % limit != 0:
        output.error(
            f"--offset ({offset}) must be a multiple of --limit ({limit})",
            kind="usage",
        )
        ctx.exit(1)
        return

    client = get_soar_client(ctx)

    # Validate status name if provided.
    if status is not None:
        if not _validate_status(ctx, client, status):
            return

    params: dict[str, Any] = _build_list_params(
        label=label,
        status=status,
        severity=severity,
        owner=owner,
        since=since,
        container_type=container_type,
        raw_filter=raw_filter,
        limit=limit,
        offset=offset,
    )

    try:
        result = client.get("container", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    rows: list[dict[str, Any]] = data
    output.render(ctx, rows, empty="No containers found.")


def _validate_status(ctx: click.Context, client: SOARClient, status: str) -> bool:
    """Check *status* against the server's container_status vocabulary.

    Returns True if valid, False after printing an error and setting exit 1.
    """
    try:
        statuses_resp = client.get("container_status")
    except SOARError as exc:
        # Can't validate — warn and pass the name through to the server.
        output.warning(
            f"could not validate status name ({exc.message}); passing through"
        )
        return True

    known: list[str] = []
    data = statuses_resp.get("data", []) if isinstance(statuses_resp, dict) else []
    for entry in data:
        if isinstance(entry, dict) and "name" in entry:
            known.append(entry["name"])

    if status not in known:
        output.error(
            f"Unknown status '{status}'. Valid: {', '.join(known)}",
            kind="usage",
        )
        ctx.exit(1)
        return False
    return True


def _build_list_params(
    *,
    label: str | None,
    status: str | None,
    severity: str | None,
    owner: str | None,
    since: str | None,
    container_type: str | None,
    raw_filter: str | None,
    limit: int | None,
    offset: int | None,
) -> dict[str, Any]:
    """Assemble query params for GET /rest/container."""
    params: dict[str, Any] = {}

    if label is not None:
        params["_filter_label"] = f'"{label}"'
    if status is not None:
        params["_filter_status"] = f'"{status}"'
    if severity is not None:
        params["_filter_severity"] = f'"{severity}"'
    if owner is not None:
        params["_filter_owner_name"] = f'"{owner}"'
    if since is not None:
        params["_filter_create_time__gt"] = f'"{since}"'
    if container_type is not None:
        api_type = _TYPE_MAP.get(container_type, container_type)
        params["_filter_container_type"] = f'"{api_type}"'

    if raw_filter is not None:
        key, _, value = raw_filter.partition("=")
        if key and value:
            params[key] = value

    if limit is not None:
        params["page_size"] = limit
        # Offset is validated upstream: requires limit, multiple of limit.
        if offset is not None and limit > 0:
            params["page"] = offset // limit

    return params


@containers_group.command("get")
@click.argument("container_id", type=int)
@click.option("--artifacts", "sub_view", flag_value="artifacts", help="Show artifacts.")
@click.option("--notes", "sub_view", flag_value="notes", help="Show notes.")
@click.option("--comments", "sub_view", flag_value="comments", help="Show comments.")
@click.option("--audit", "sub_view", flag_value="audit", help="Show audit log.")
@click.option(
    "--activity",
    "sub_view",
    flag_value="activity",
    help="Show activity feed.",
)
@click.option(
    "--playbook-runs",
    "sub_view",
    flag_value="playbook_runs",
    help="Show playbook runs.",
)
@click.option("--phases", "sub_view", flag_value="phases", help="Show case phases.")
@click.pass_context
def get_cmd(
    ctx: click.Context,
    *,
    container_id: int,
    sub_view: str | None,
) -> None:
    """Get a container by ID, optionally showing a sub-view."""
    client = get_soar_client(ctx)

    if sub_view is not None:
        suffix = _SUB_VIEWS[sub_view]
        path = f"container/{container_id}/{suffix}"
    else:
        path = f"container/{container_id}"

    try:
        result = client.get(path, params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    payload = _extract_payload(result, sub_view)
    label = sub_view or "data"
    empty_msg = f"No {label} found for container {container_id}."
    output.render(ctx, payload, empty=empty_msg)


def _extract_payload(
    result: Any,
    sub_view: str | None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Normalize a get response for output.render."""
    if sub_view is None:
        # Single container object.
        if isinstance(result, dict):
            return result
        return {}
    # Sub-view: paginated envelope or raw shape.
    if isinstance(result, dict) and "data" in result:
        inner = result["data"]
        if isinstance(inner, list):
            return inner
        if isinstance(inner, dict):
            return inner
        return {}
    if isinstance(result, list):
        return result
    return {}
