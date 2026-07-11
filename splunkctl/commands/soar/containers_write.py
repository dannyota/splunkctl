"""SOAR container writes — create, update, close, assign, delete."""

from __future__ import annotations

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar.containers import containers_group
from splunkctl.soar.client import SOARClient, SOARError


def _sdi_precheck(
    client: SOARClient,
    sdi: str,
) -> int | None:
    """Return existing container id if *sdi* is already in use, else None."""
    params = {"_filter_source_data_identifier": f'"{sdi}"', "page_size": 1}
    try:
        result = client.get("container", params=params)
    except SOARError:
        return None
    data = result.get("data", []) if isinstance(result, dict) else []
    if data and isinstance(data[0], dict):
        return int(data[0]["id"])
    return None


def _read_modify_write_tags(
    client: SOARClient,
    container_id: int,
    add_tags: tuple[str, ...],
) -> list[str]:
    """Fetch existing tags, merge *add_tags*, return the merged list."""
    existing: list[str] = []
    try:
        result = client.get(f"container/{container_id}", params={})
        if isinstance(result, dict):
            existing = list(result.get("tags", []))
    except SOARError:
        pass
    merged = list(dict.fromkeys(existing + list(add_tags)))
    return merged


def _build_create_payload(
    *,
    name: str,
    label: str,
    severity: str | None,
    sensitivity: str | None,
    sdi: str | None,
    description: str | None,
    tags: tuple[str, ...],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble container create payload."""
    body: dict[str, Any] = {
        "name": name,
        "label": label,
        "run_automation": False,
    }
    if severity is not None:
        body["severity"] = severity
    if sensitivity is not None:
        body["sensitivity"] = sensitivity
    if sdi is not None:
        body["source_data_identifier"] = sdi
    if description is not None:
        body["description"] = description
    if tags:
        body["tags"] = list(tags)
    for field in fields:
        key, _, value = field.partition("=")
        if key and value:
            body.setdefault("custom_fields", {})[key] = value
    return body


def _build_update_payload(
    *,
    name: str | None,
    label: str | None,
    severity: str | None,
    sensitivity: str | None,
    description: str | None,
    status: str | None,
    owner: str | None,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble container update payload."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if label is not None:
        body["label"] = label
    if severity is not None:
        body["severity"] = severity
    if sensitivity is not None:
        body["sensitivity"] = sensitivity
    if description is not None:
        body["description"] = description
    if status is not None:
        body["status"] = status
    if owner is not None:
        body["owner_name"] = owner
    for field in fields:
        key, _, value = field.partition("=")
        if key and value:
            body.setdefault("custom_fields", {})[key] = value
    return body


@containers_group.command("create")
@guard.guarded
@click.option("--name", required=True, help="Container name.")
@click.option("--label", required=True, help="Container label (e.g. events).")
@click.option("--severity", default=None, help="Severity name.")
@click.option("--sensitivity", default=None, help="Sensitivity level.")
@click.option("--sdi", default=None, help="Source data identifier (SDI).")
@click.option("--description", default=None, help="Description text.")
@click.option("--tag", "tags", multiple=True, help="Tag (repeatable).")
@click.option(
    "--field",
    "fields",
    multiple=True,
    help="Custom field key=value (repeatable).",
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    *,
    name: str,
    label: str,
    severity: str | None,
    sensitivity: str | None,
    sdi: str | None,
    description: str | None,
    tags: tuple[str, ...],
    fields: tuple[str, ...],
) -> None:
    """Create a container. SDI dedup precheck when --sdi is given."""
    body = _build_create_payload(
        name=name,
        label=label,
        severity=severity,
        sensitivity=sensitivity,
        sdi=sdi,
        description=description,
        tags=tags,
        fields=fields,
    )
    details = json.dumps(body, indent=2)
    if not guard.soar_check(ctx, f"Create container '{name}'", details=details):
        return

    client = get_soar_client(ctx)

    # SDI dedup precheck.
    if sdi is not None:
        existing = _sdi_precheck(client, sdi)
        if existing is not None:
            output.error(
                f"SDI '{sdi}' already exists on container {existing}",
                kind="conflict",
            )
            ctx.exit(1)
            return

    try:
        result = client.post("container", body=body)
    except SOARError as exc:
        # Surface existing_container_id from a server-side SDI duplicate.
        eid = exc.data.get("existing_container_id")
        if eid is not None:
            output.error(
                f"{exc.message} (existing_container_id={eid})",
                kind=exc.kind,
                http_status=exc.http_status,
            )
        else:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Container created: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


@containers_group.command("update")
@guard.guarded
@click.argument("ids", nargs=-1, required=True, type=int)
@click.option("--name", default=None, help="New name.")
@click.option("--label", default=None, help="New label.")
@click.option("--severity", default=None, help="New severity.")
@click.option("--sensitivity", default=None, help="New sensitivity.")
@click.option("--description", default=None, help="New description.")
@click.option("--status", default=None, help="New status (by NAME, not id).")
@click.option("--owner", default=None, help="New owner username.")
@click.option("--tag", "tags", multiple=True, help="Tag to add (repeatable).")
@click.option(
    "--field",
    "fields",
    multiple=True,
    help="Custom field key=value (repeatable).",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    ids: tuple[int, ...],
    *,
    name: str | None,
    label: str | None,
    severity: str | None,
    sensitivity: str | None,
    description: str | None,
    status: str | None,
    owner: str | None,
    tags: tuple[str, ...],
    fields: tuple[str, ...],
) -> None:
    """Update one or more containers (bulk via single array POST)."""
    if isinstance(status, int) or (isinstance(status, str) and status.isdigit()):
        output.error(
            f"Status must be a name (e.g. 'closed'), not a numeric id: {status}",
            kind="usage",
        )
        ctx.exit(1)
        return

    body = _build_update_payload(
        name=name,
        label=label,
        severity=severity,
        sensitivity=sensitivity,
        description=description,
        status=status,
        owner=owner,
        fields=fields,
    )
    if not body and not tags:
        output.error(
            "No updates specified. Use --name, --status, --severity, etc.",
            kind="usage",
        )
        ctx.exit(1)
        return

    client = get_soar_client(ctx)

    # Tags: read-modify-write per container, merge into body.
    if tags:
        for cid in ids:
            merged = _read_modify_write_tags(client, cid, tags)
            body["tags"] = merged

    id_str = ", ".join(str(i) for i in ids)
    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Update container(s) {id_str}",
        details=details,
    ):
        return

    if len(ids) == 1:
        try:
            result = client.post(f"container/{ids[0]}", body=body)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Container {ids[0]} updated.")
        if isinstance(result, dict) and result:
            output.render(ctx, result)
    else:
        # Bulk: one array POST to /rest/container.
        bulk = [{"id": cid, **body} for cid in ids]
        try:
            result = client.post("container", body=bulk)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Containers updated: {id_str}")
        if isinstance(result, dict) and result:
            output.render(ctx, result)


@containers_group.command("close")
@guard.guarded
@click.argument("ids", nargs=-1, required=True, type=int)
@click.pass_context
def close_cmd(ctx: click.Context, ids: tuple[int, ...]) -> None:
    """Close one or more containers (sugar for update --status closed)."""
    id_str = ", ".join(str(i) for i in ids)
    body = {"status": "closed"}
    details = json.dumps(body, indent=2)

    if not guard.soar_check(
        ctx,
        f"Close container(s) {id_str}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)

    if len(ids) == 1:
        try:
            client.post(f"container/{ids[0]}", body=body)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Container {ids[0]} closed.")
    else:
        bulk = [{"id": cid, **body} for cid in ids]
        try:
            client.post("container", body=bulk)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Containers closed: {id_str}")


@containers_group.command("assign")
@guard.guarded
@click.argument("ids", nargs=-1, required=True, type=int)
@click.option("--owner", default=None, help="Owner username.")
@click.option("--role", default=None, help="Role name.")
@click.pass_context
def assign_cmd(
    ctx: click.Context,
    ids: tuple[int, ...],
    *,
    owner: str | None,
    role: str | None,
) -> None:
    """Assign owner and/or role to containers (bulk)."""
    body: dict[str, Any] = {}
    if owner is not None:
        body["owner_name"] = owner
    if role is not None:
        body["role"] = role
    if not body:
        output.error(
            "Provide --owner and/or --role.",
            kind="usage",
        )
        ctx.exit(1)
        return

    id_str = ", ".join(str(i) for i in ids)
    details = json.dumps(body, indent=2)
    if not guard.soar_check(
        ctx,
        f"Assign container(s) {id_str}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)

    if len(ids) == 1:
        try:
            client.post(f"container/{ids[0]}", body=body)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Container {ids[0]} assigned.")
    else:
        bulk = [{"id": cid, **body} for cid in ids]
        try:
            client.post("container", body=bulk)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        output.info(f"Containers assigned: {id_str}")


@containers_group.command("delete")
@guard.guarded
@click.argument("ids", nargs=-1, required=True, type=int)
@click.pass_context
def delete_cmd(ctx: click.Context, ids: tuple[int, ...]) -> None:
    """Delete containers (requires Basic auth credentials)."""
    id_str = ", ".join(str(i) for i in ids)
    if not guard.soar_check(ctx, f"Delete container(s) {id_str}"):
        return

    client = get_soar_client(ctx)
    errors: list[str] = []
    for cid in ids:
        try:
            client.delete(f"container/{cid}")
            output.info(f"Container {cid} deleted.")
        except SOARError as exc:
            errors.append(f"container {cid}: {exc.message}")

    if errors:
        output.error("; ".join(errors))
        ctx.exit(1)
