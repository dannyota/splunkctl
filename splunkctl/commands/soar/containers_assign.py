"""SOAR container assignment — owner/role resolution, verification, assign."""

from __future__ import annotations

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar.containers import containers_group
from splunkctl.soar.client import SOARClient, SOARError


def resolve_owner_role(
    client: SOARClient,
    owner: str | None,
    role: str | None,
) -> dict[str, Any]:
    """Resolve owner/role names to the numeric ids the API honors.

    The container endpoint returns success but silently IGNORES
    name-shaped fields (``owner_name``, ``role``) on write — only
    ``owner_id``/``role_id`` stick. Raises SOARError on unknown names.
    """
    resolved: dict[str, Any] = {}
    for key, endpoint, field, value in (
        ("owner_id", "ph_user", "username", owner),
        ("role_id", "role", "name", role),
    ):
        if value is None:
            continue
        if value.isdigit():
            resolved[key] = int(value)
            continue
        result = client.get(endpoint, params={f"_filter_{field}": json.dumps(value)})
        data = result.get("data", []) if isinstance(result, dict) else []
        if not data:
            raise SOARError(
                f"{field.capitalize()} '{value}' not found on SOAR.",
                kind="not_found",
            )
        resolved[key] = int(data[0]["id"])
    return resolved


def verify_owner_role(
    client: SOARClient,
    cid: int,
    resolved: dict[str, Any],
) -> list[str]:
    """Read back a container and report owner/role writes that didn't stick."""
    try:
        got = client.get(f"container/{cid}", params={})
    except SOARError:
        return []
    problems: list[str] = []
    if "owner_id" in resolved and got.get("owner") != resolved["owner_id"]:
        problems.append(f"owner is still {got.get('owner_name') or got.get('owner')!r}")
    if "role_id" in resolved and got.get("role") != resolved["role_id"]:
        problems.append(f"role is still {got.get('role')!r}")
    return problems


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
    """Assign an owner OR a role to containers (bulk)."""
    if owner is None and role is None:
        output.error(
            "Provide --owner or --role.",
            kind="usage",
        )
        ctx.exit(1)
        return
    if owner is not None and role is not None:
        output.error(
            "Provide either --owner or --role, not both — SOAR assigns a "
            "container to a single principal (assigning a role clears the "
            "owner, and vice versa).",
            kind="usage",
        )
        ctx.exit(1)
        return

    id_str = ", ".join(str(i) for i in ids)
    preview: dict[str, Any] = {}
    if owner is not None:
        preview["owner"] = f"{owner} (resolved to owner_id at apply time)"
    if role is not None:
        preview["role"] = f"{role} (resolved to role_id at apply time)"
    details = json.dumps(preview, indent=2)
    if not guard.soar_check(
        ctx,
        f"Assign container(s) {id_str}",
        details=details,
    ):
        return

    client = get_soar_client(ctx)
    try:
        body = resolve_owner_role(client, owner, role)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    try:
        if len(ids) == 1:
            client.post(f"container/{ids[0]}", body=body)
        else:
            client.post(
                "container",
                body=[{"id": cid, **body} for cid in ids],
            )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    output.info(f"Container(s) assigned: {id_str}")

    problems = verify_owner_role(client, ids[0], body)
    if problems:
        output.error(
            f"Server accepted the assign but it did not stick: {'; '.join(problems)}.",
            kind="error",
        )
        ctx.exit(1)
