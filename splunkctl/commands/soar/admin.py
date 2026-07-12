"""SOAR admin — users, roles, audit log."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError


def _cap_csv(text: str, limit: int) -> str:
    """Truncate CSV *text* to header + *limit* rows (quote-aware)."""
    reader = csv.reader(io.StringIO(text))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for i, row in enumerate(reader):
        if i > limit:
            break
        writer.writerow(row)
    return buf.getvalue()


# ── users ────────────────────────────────────────────────────────────

_AUTH_PROVISION_NOTICE = (
    "Token provisioning: the automation token plaintext is shown ONCE "
    "in the SOAR UI at creation time. It cannot be retrieved via REST — "
    "GET .../token returns only the hashed key. Paste the token from "
    "the UI into your CLI profile or environment variable."
)


@click.group("users")
def users_group() -> None:
    """SOAR user management (ph_user)."""


@users_group.command("list")
@click.option(
    "--type",
    "user_type",
    default=None,
    type=click.Choice(["normal", "automation"]),
    help="Filter by user type. 'automation' surfaces the hidden system user.",
)
@click.pass_context
def users_list(ctx: click.Context, *, user_type: str | None) -> None:
    """List SOAR users. The system automation user is hidden by default."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {"page_size": 200}
    if user_type is not None:
        params["_filter_type"] = json.dumps(user_type)
    try:
        result = client.get("ph_user", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    rows = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, rows, empty="No users found.")


@users_group.command("get")
@click.argument("user_id", type=int)
@click.pass_context
def users_get(ctx: click.Context, *, user_id: int) -> None:
    """Get a SOAR user by ID."""
    client = get_soar_client(ctx)
    try:
        result = client.get(f"ph_user/{user_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"User {user_id} not found.")


@users_group.command("create")
@guard.guarded
@click.option("--username", required=True, help="Username.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=False,
    help="Password (prompted securely if omitted).",
)
@click.option(
    "--type",
    "user_type",
    default="normal",
    type=click.Choice(["normal", "automation"]),
    help="User type (default: normal).",
)
@click.option("--role", "roles", multiple=True, help="Role name (repeatable).")
@click.option(
    "--allowed-ip",
    "allowed_ips",
    multiple=True,
    help="Allowed IP for automation user (repeatable).",
)
@click.option("--first-name", default=None, help="First name.")
@click.option("--last-name", default=None, help="Last name.")
@click.pass_context
def users_create(
    ctx: click.Context,
    *,
    username: str,
    password: str,
    user_type: str,
    roles: tuple[str, ...],
    allowed_ips: tuple[str, ...],
    first_name: str | None,
    last_name: str | None,
) -> None:
    """Create a SOAR user."""
    body: dict[str, Any] = {
        "username": username,
        "password": password,
        "type": user_type,
    }
    if roles:
        body["roles"] = list(roles)
    if allowed_ips:
        body["allowed_ips"] = list(allowed_ips)
    if first_name is not None:
        body["first_name"] = first_name
    if last_name is not None:
        body["last_name"] = last_name

    preview = {k: v for k, v in body.items() if k != "password"}
    preview["password"] = "********"  # noqa: S105
    details = json.dumps(preview, indent=2)
    if not guard.soar_check(ctx, f"Create user '{username}'", details=details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("ph_user", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"User created: id={new_id}")
    if user_type == "automation":
        output.info(_AUTH_PROVISION_NOTICE)
    if isinstance(result, dict):
        output.render(ctx, result)


def _fetch_current_roles(
    client: Any,
    user_id: int,
) -> list[int]:
    """Fetch the current role ids for a user."""
    user = client.get(f"ph_user/{user_id}")
    if isinstance(user, dict):
        role_ids = user.get("roles", [])
        if isinstance(role_ids, list):
            return [int(r) for r in role_ids]
    return []


def _resolve_role_ids(
    client: Any,
    role_names: tuple[str, ...],
) -> list[int]:
    """Resolve role names to ids via GET /rest/role."""
    if not role_names:
        return []
    result = client.get("role", params={"page_size": 200})
    data = result.get("data", []) if isinstance(result, dict) else []
    name_map: dict[str, int] = {}
    for role in data:
        if isinstance(role, dict) and "name" in role and "id" in role:
            name_map[role["name"]] = int(role["id"])
    ids: list[int] = []
    for name in role_names:
        if name in name_map:
            ids.append(name_map[name])
        else:
            output.warning(f"role '{name}' not found — skipping")
    return ids


@users_group.command("update")
@guard.guarded
@click.argument("user_id", type=int)
@click.option(
    "--password",
    default=None,
    help="New password (masked in preview).",
)
@click.option(
    "--add-role",
    "add_roles",
    multiple=True,
    help="Role name to add (repeatable).",
)
@click.option(
    "--remove-role",
    "remove_roles",
    multiple=True,
    help="Role name to remove (repeatable).",
)
@click.option("--first-name", default=None, help="New first name.")
@click.option("--last-name", default=None, help="New last name.")
@click.option(
    "--allowed-ip",
    "allowed_ips",
    multiple=True,
    help="Replace allowed IPs (repeatable).",
)
@click.pass_context
def users_update(
    ctx: click.Context,
    *,
    user_id: int,
    password: str | None,
    add_roles: tuple[str, ...],
    remove_roles: tuple[str, ...],
    first_name: str | None,
    last_name: str | None,
    allowed_ips: tuple[str, ...],
) -> None:
    """Update a SOAR user (password, roles, profile)."""
    has_changes = (
        password is not None
        or add_roles
        or remove_roles
        or first_name is not None
        or last_name is not None
        or allowed_ips
    )
    if not has_changes:
        output.error(
            "No updates specified. Use --password, --add-role, "
            "--remove-role, --first-name, --last-name, or --allowed-ip.",
            kind="usage",
        )
        ctx.exit(1)
        return

    preview_parts: list[str] = []
    if password is not None:
        preview_parts.append("password: ********")
    if add_roles:
        preview_parts.append(f"add roles: {list(add_roles)}")
    if remove_roles:
        preview_parts.append(f"remove roles: {list(remove_roles)}")
    if first_name is not None:
        preview_parts.append(f"first_name: {first_name}")
    if last_name is not None:
        preview_parts.append(f"last_name: {last_name}")
    if allowed_ips:
        preview_parts.append(f"allowed_ips: {list(allowed_ips)}")

    details = "\n".join(preview_parts)
    if not guard.soar_check(ctx, f"Update user {user_id}", details=details):
        return

    client = get_soar_client(ctx)

    body: dict[str, Any] = {}
    if password is not None:
        body["password"] = password
    if first_name is not None:
        body["first_name"] = first_name
    if last_name is not None:
        body["last_name"] = last_name
    if allowed_ips:
        body["allowed_ips"] = list(allowed_ips)

    # Read-modify-write for roles.
    if add_roles or remove_roles:
        current_ids = _fetch_current_roles(client, user_id)
        add_ids = _resolve_role_ids(client, add_roles)
        remove_ids = set(_resolve_role_ids(client, remove_roles))
        merged = list(dict.fromkeys(current_ids + add_ids))
        merged = [rid for rid in merged if rid not in remove_ids]
        body["roles"] = merged

    try:
        result = client.post(f"ph_user/{user_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"User {user_id} updated.")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


@users_group.command("delete")
@guard.guarded
@click.argument("user_id", type=int)
@click.pass_context
def users_delete(ctx: click.Context, *, user_id: int) -> None:
    """Delete (soft-delete) a SOAR user.

    SOAR DELETE sets is_active=False — the user is deactivated, not
    removed. Their automation token returns "User is inactive" afterward.
    """
    details = (
        "SOAR user deletion is a SOFT DELETE (is_active=False).\n"
        "The user record remains; their token errors 'User is inactive'."
    )
    if not guard.soar_check(ctx, f"Delete user {user_id}", details=details):
        return

    client = get_soar_client(ctx)
    try:
        client.delete(f"ph_user/{user_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    output.info(f"User {user_id} soft-deleted (is_active=False).")


@users_group.command("token")
@click.argument("user_id", type=int)
@click.pass_context
def users_token(ctx: click.Context, *, user_id: int) -> None:
    """Show the hashed token info for a user.

    This is NOT the usable token. The plaintext is shown once in the
    SOAR UI at creation; REST only returns the hashed key and expiry.
    """
    client = get_soar_client(ctx)
    try:
        result = client.get(f"ph_user/{user_id}/token")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"No token info for user {user_id}.")
    if output.is_table(ctx):
        output.info(
            "Note: the 'key' above is the HASHED token — not the "
            "usable plaintext. " + _AUTH_PROVISION_NOTICE
        )


# ── roles ────────────────────────────────────────────────────────────


@click.group("roles")
def roles_group() -> None:
    """SOAR role management (7 immutable built-in roles)."""


@roles_group.command("list")
@click.pass_context
def roles_list(ctx: click.Context) -> None:
    """List all SOAR roles with permissions."""
    client = get_soar_client(ctx)
    try:
        result = client.get("role", params={"page_size": 200})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    rows = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, rows, empty="No roles found.")


@roles_group.command("get")
@click.argument("role_id", type=int)
@click.pass_context
def roles_get(ctx: click.Context, *, role_id: int) -> None:
    """Get a SOAR role by ID (includes permission matrix)."""
    client = get_soar_client(ctx)
    try:
        result = client.get(f"role/{role_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"Role {role_id} not found.")


# ── audit ────────────────────────────────────────────────────────────


@click.command("audit")
@click.option("--user", "user_filter", default=None, help="Filter by username.")
@click.option(
    "--playbook",
    "playbook_filter",
    default=None,
    help="Filter by playbook name.",
)
@click.option(
    "--container",
    "container_filter",
    default=None,
    type=int,
    help="Filter by container ID.",
)
@click.option("--start", default=None, help="Start time (ISO 8601).")
@click.option("--end", default=None, help="End time (ISO 8601).")
@click.option(
    "--format",
    "out_format",
    default=None,
    type=click.Choice(["csv"]),
    help="Request CSV from server.",
)
@click.option(
    "--limit",
    default=None,
    type=click.IntRange(min=1),
    help="Max rows.",
)
@click.pass_context
def audit_cmd(
    ctx: click.Context,
    *,
    user_filter: str | None,
    playbook_filter: str | None,
    container_filter: int | None,
    start: str | None,
    end: str | None,
    out_format: str | None,
    limit: int | None,
) -> None:
    """Query the SOAR audit log (bare-array endpoint, normalized)."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {}
    if user_filter is not None:
        params["_filter_username__icontains"] = json.dumps(user_filter)
    if playbook_filter is not None:
        params["_filter_playbook__icontains"] = json.dumps(playbook_filter)
    if container_filter is not None:
        params["_filter_container"] = str(container_filter)
    if start is not None:
        params["start"] = start
    if end is not None:
        params["end"] = end
    if limit is not None:
        params["page_size"] = limit

    # CSV: the server returns raw CSV text (Content-Type: application/csv),
    # not JSON. Fetch as bytes and print directly.
    if out_format == "csv":
        params["format"] = "csv"
        try:
            raw = client.get_bytes("audit", params=params)
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return
        text = raw.decode("utf-8")
        if limit is not None:
            # The bare-array audit endpoint ignores page_size — enforce
            # the row cap client-side here too, not just for JSON.
            text = _cap_csv(text, limit)
        click.echo(text, nl=False)
        return

    try:
        result = client.get("audit", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    rows = result.get("data", []) if isinstance(result, dict) else []
    if limit is not None:
        # The bare-array audit endpoint ignores page_size — enforce
        # the row cap client-side.
        rows = rows[:limit]
    output.render(ctx, rows, empty="No audit entries found.")
