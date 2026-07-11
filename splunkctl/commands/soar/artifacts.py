"""SOAR artifact CRUD — list, get, create, update, delete."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.guard import guarded, soar_check
from splunkctl.soar.cimcef import CEF_CONTAINS_MAP
from splunkctl.soar.client import SOARError


def _parse_cef_pairs(raw: tuple[str, ...]) -> dict[str, str]:
    """Parse ``key=value`` pairs into a CEF dict."""
    cef: dict[str, str] = {}
    for pair in raw:
        key, _, value = pair.partition("=")
        if not key:
            continue
        cef[key] = value
    return cef


def _parse_cef_type_pairs(raw: tuple[str, ...]) -> dict[str, list[str]]:
    """Parse ``field=type`` pairs into a cef_types dict."""
    types: dict[str, list[str]] = {}
    for pair in raw:
        key, _, value = pair.partition("=")
        if not key:
            continue
        types[key] = [value]
    return types


def _auto_cef_types(
    cef: dict[str, Any],
    explicit: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Build cef_types from the built-in map, overridden by explicit entries."""
    types: dict[str, list[str]] = {}
    for key in cef:
        if key in explicit:
            types[key] = explicit[key]
        elif key in CEF_CONTAINS_MAP:
            types[key] = CEF_CONTAINS_MAP[key]
    return types


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group("artifacts")
def artifacts_group() -> None:
    """Artifact CRUD — list, get, create, update, delete."""


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@artifacts_group.command("list")
@click.option(
    "--container",
    "container_id",
    required=True,
    type=int,
    help="Container ID to list artifacts for.",
)
@click.option("--limit", default=None, type=click.IntRange(min=1), help="Page size.")
@click.option("--offset", default=None, type=click.IntRange(min=0), help="Row offset.")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    container_id: int,
    limit: int | None,
    offset: int | None,
) -> None:
    """List artifacts in a container."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {"_filter_container": container_id}
    if limit is not None:
        params["page_size"] = limit
        if offset is not None and limit > 0:
            params["page"] = offset // limit
    elif offset is not None:
        output.error("--offset requires --limit", kind="usage")
        ctx.exit(1)
        return

    try:
        result = client.get("artifact", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No artifacts found.")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@artifacts_group.command("get")
@click.argument("artifact_id", type=int)
@click.pass_context
def get_cmd(ctx: click.Context, *, artifact_id: int) -> None:
    """Get an artifact by ID."""
    client = get_soar_client(ctx)
    try:
        result = client.get(f"artifact/{artifact_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"No artifact {artifact_id} found.")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@artifacts_group.command("create")
@guarded
@click.option(
    "--container",
    "container_id",
    required=True,
    type=int,
    help="Container to add the artifact to.",
)
@click.option("--name", required=True, help="Artifact name.")
@click.option(
    "--cef",
    "cef_pairs",
    multiple=True,
    help="CEF key=value (repeatable).",
)
@click.option(
    "--cef-file",
    type=click.Path(exists=True),
    default=None,
    help="JSON file with CEF fields.",
)
@click.option(
    "--cef-type",
    "cef_type_pairs",
    multiple=True,
    help="Explicit contains type: field=type (repeatable).",
)
@click.option("--sdi", default=None, help="source_data_identifier for dedup.")
@click.option("--severity", default=None, help="Artifact severity.")
@click.option("--type", "artifact_type", default=None, help="Artifact type.")
@click.option(
    "--no-automation",
    is_flag=True,
    default=False,
    help="Suppress playbook automation on this artifact.",
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    *,
    container_id: int,
    name: str,
    cef_pairs: tuple[str, ...],
    cef_file: str | None,
    cef_type_pairs: tuple[str, ...],
    sdi: str | None,
    severity: str | None,
    artifact_type: str | None,
    no_automation: bool,
) -> None:
    """Create an artifact in a container."""
    client = get_soar_client(ctx)

    # Build CEF dict from --cef and --cef-file
    cef: dict[str, Any] = {}
    if cef_file:
        cef = json.loads(Path(cef_file).read_text())
    cef.update(_parse_cef_pairs(cef_pairs))

    # Build cef_types with auto-population from CEF_CONTAINS_MAP
    explicit_types = _parse_cef_type_pairs(cef_type_pairs)
    cef_types = _auto_cef_types(cef, explicit_types)

    # Client-side SDI dedup precheck
    if sdi is not None:
        try:
            existing = client.get(
                "artifact",
                params={
                    "_filter_source_data_identifier": f'"{sdi}"',
                    "_filter_container": container_id,
                },
            )
            data = existing.get("data", []) if isinstance(existing, dict) else []
            if data:
                eid = data[0].get("id", "?")
                output.warning(
                    f"SDI '{sdi}' already exists as artifact {eid} "
                    f"in container {container_id} (server does not dedup)"
                )
        except SOARError as exc:
            output.warning(
                f"could not verify SDI uniqueness ({exc.message}); proceeding"
            )

    # Build payload
    payload: dict[str, Any] = {
        "container_id": container_id,
        "name": name,
    }
    if cef:
        payload["cef"] = cef
    if cef_types:
        payload["cef_types"] = cef_types
    if sdi is not None:
        payload["source_data_identifier"] = sdi
    if severity is not None:
        payload["severity"] = severity
    if artifact_type is not None:
        payload["type"] = artifact_type
    if no_automation:
        payload["run_automation"] = False

    details = json.dumps(payload, indent=2, default=str)
    if not soar_check(ctx, f"Create artifact '{name}'", details=details):
        return

    try:
        result = client.post("artifact", body=payload)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result if isinstance(result, dict) else {"success": True})


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@artifacts_group.command("update")
@guarded
@click.argument("artifact_id", type=int)
@click.option("--name", default=None, help="New artifact name.")
@click.option(
    "--cef",
    "cef_pairs",
    multiple=True,
    help="CEF key=value to merge (repeatable).",
)
@click.option(
    "--cef-file",
    type=click.Path(exists=True),
    default=None,
    help="JSON file with CEF fields to merge.",
)
@click.option(
    "--replace-cef",
    is_flag=True,
    default=False,
    help="Replace cef{} wholesale instead of merging.",
)
@click.option("--severity", default=None, help="New severity.")
@click.option("--type", "artifact_type", default=None, help="New type.")
@click.pass_context
def update_cmd(
    ctx: click.Context,
    *,
    artifact_id: int,
    name: str | None,
    cef_pairs: tuple[str, ...],
    cef_file: str | None,
    replace_cef: bool,
    severity: str | None,
    artifact_type: str | None,
) -> None:
    """Update an artifact (fetch-merge for CEF by default)."""
    client = get_soar_client(ctx)

    # New CEF from flags
    new_cef: dict[str, Any] = {}
    if cef_file:
        new_cef = json.loads(Path(cef_file).read_text())
    new_cef.update(_parse_cef_pairs(cef_pairs))

    has_cef = bool(new_cef)

    # Fetch existing artifact for merge (unless --replace-cef)
    if has_cef and not replace_cef:
        try:
            existing = client.get(f"artifact/{artifact_id}", params={})
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        old_cef: dict[str, Any] = (
            existing.get("cef", {}) if isinstance(existing, dict) else {}
        )
        merged_cef = {**old_cef, **new_cef}
    elif has_cef:
        merged_cef = new_cef
    else:
        merged_cef = {}

    # Build payload
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if has_cef:
        payload["cef"] = merged_cef
    if severity is not None:
        payload["severity"] = severity
    if artifact_type is not None:
        payload["type"] = artifact_type

    if not payload:
        output.error("Nothing to update — provide at least one field.", kind="usage")
        ctx.exit(1)
        return

    details = json.dumps(payload, indent=2, default=str)
    if not soar_check(ctx, f"Update artifact {artifact_id}", details=details):
        return

    try:
        result = client.post(f"artifact/{artifact_id}", body=payload)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result if isinstance(result, dict) else {"success": True})


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@artifacts_group.command("delete")
@guarded
@click.argument("artifact_id", type=int)
@click.pass_context
def delete_cmd(ctx: click.Context, *, artifact_id: int) -> None:
    """Delete an artifact by ID."""
    client = get_soar_client(ctx)

    if not soar_check(ctx, f"Delete artifact {artifact_id}"):
        return

    try:
        result = client.delete(f"artifact/{artifact_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result if isinstance(result, dict) else {"id": artifact_id})
