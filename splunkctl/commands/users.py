"""User and role management commands."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import fetch_page, list_options, parse_set

_MAX_CAPS = 5

_DETAIL_FIELDS = (
    "realname",
    "email",
    "roles",
    "defaultApp",
    "type",
    "tz",
    "lang",
    "last_successful_login",
    "locked-out",
    "capabilities",
)


def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else ""


def _user_row(user: Any) -> dict[str, Any]:
    c: dict[str, Any] = user.content
    return {
        "name": user.name,
        "realname": c.get("realname", ""),
        "email": c.get("email", ""),
        "roles": _format_list(c.get("roles", [])),
        "defaultApp": c.get("defaultApp", ""),
        "type": c.get("type", ""),
    }


def _caps_str(val: Any, *, truncate: bool) -> str:
    caps = val if isinstance(val, list) else [val] if val else []
    if truncate and len(caps) > _MAX_CAPS:
        return ", ".join(caps[:_MAX_CAPS]) + f" (+{len(caps) - _MAX_CAPS} more)"
    return ", ".join(caps)


def _user_detail(user: Any, *, truncate: bool) -> dict[str, Any]:
    c: dict[str, Any] = user.content
    row: dict[str, Any] = {"name": user.name}
    for f in _DETAIL_FIELDS:
        val = c.get(f, "")
        if f == "capabilities":
            row[f] = _caps_str(val, truncate=truncate)
        elif isinstance(val, list):
            row[f] = _format_list(val)
        else:
            row[f] = val
    return row


def _role_row(role: Any, *, truncate: bool) -> dict[str, Any]:
    c: dict[str, Any] = role.content
    imported = c.get("imported_roles", [])
    if isinstance(imported, str):
        imported = [imported]
    return {
        "name": role.name,
        "imported_roles": ", ".join(imported),
        "capabilities": _caps_str(c.get("capabilities", []), truncate=truncate),
        "defaultApp": c.get("defaultApp", ""),
    }


@click.group("users")
def users_group() -> None:
    """Manage users and roles."""


@users_group.command("list")
@list_options
@click.pass_context
def list_users(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List all users."""
    client = get_client(ctx)
    users = fetch_page(
        client.service.users.list,
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows = [_user_row(u) for u in users]
    output.render(ctx, rows, empty="No users found.")


@users_group.command("get")
@click.argument("name")
@click.pass_context
def get_user(ctx: click.Context, name: str) -> None:
    """Get details for a single user."""
    client = get_client(ctx)
    try:
        user = client.service.users[name]
    except KeyError:
        output.error(f"User '{name}' not found.")
        ctx.exit(1)
        return
    output.render(ctx, _user_detail(user, truncate=output.is_table(ctx)))


# --- roles sub-group ---


@users_group.group("roles", invoke_without_command=True)
@list_options
@click.pass_context
def roles_group(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """Manage roles (bare invocation lists all roles)."""
    if ctx.invoked_subcommand is None:
        client = get_client(ctx)
        roles = fetch_page(
            client.service.roles.list,
            limit=limit,
            offset=offset,
            name_filter=name_filter,
        )
        truncate = output.is_table(ctx)
        rows = [_role_row(r, truncate=truncate) for r in roles]
        output.render(ctx, rows, empty="No roles found.")


@roles_group.command("get")
@click.argument("name")
@click.pass_context
def get_role(ctx: click.Context, name: str) -> None:
    """Get full role details."""
    client = get_client(ctx)
    try:
        role = client.service.roles[name]
    except KeyError:
        output.error(f"Role '{name}' not found.")
        ctx.exit(1)
        return
    c: dict[str, Any] = role.content
    imported = c.get("imported_roles", [])
    if isinstance(imported, str):
        imported = [imported]
    row: dict[str, Any] = {
        "name": role.name,
        "imported_roles": ", ".join(imported),
        "capabilities": _caps_str(c.get("capabilities", []), truncate=False),
        "defaultApp": c.get("defaultApp", ""),
        "srchIndexesAllowed": _format_list(c.get("srchIndexesAllowed", [])),
        "srchFilter": c.get("srchFilter", ""),
    }
    output.render(ctx, row)


@roles_group.command("create")
@guard.guarded
@click.argument("name")
@click.option(
    "--capabilities",
    default=None,
    help="Comma-separated capabilities.",
)
@click.option(
    "--imported-roles",
    default=None,
    help="Comma-separated imported roles.",
)
@click.option(
    "--search-indexes",
    default=None,
    help="Comma-separated allowed indexes.",
)
@click.option("--search-filter", default=None, help="Search filter.")
@click.option("--default-app", default=None, help="Default app.")
@click.option("--set", "set_pairs", multiple=True, help="KEY=VALUE extra fields.")
@click.pass_context
def create_role(
    ctx: click.Context,
    name: str,
    capabilities: str | None,
    imported_roles: str | None,
    search_indexes: str | None,
    search_filter: str | None,
    default_app: str | None,
    set_pairs: tuple[str, ...],
) -> None:
    """Create a new role."""
    kwargs: dict[str, Any] = {}
    if set_pairs:
        kwargs.update(parse_set(set_pairs))
    if capabilities:
        kwargs["capabilities"] = [c.strip() for c in capabilities.split(",")]
    if imported_roles:
        kwargs["imported_roles"] = [r.strip() for r in imported_roles.split(",")]
    if search_indexes:
        kwargs["srchIndexesAllowed"] = [i.strip() for i in search_indexes.split(",")]
    if search_filter:
        kwargs["srchFilter"] = search_filter
    if default_app:
        kwargs["defaultApp"] = default_app
    details = f"  role: {name}"
    for k, v in kwargs.items():
        details += f"\n  {k}: {v}"
    if not guard.check(ctx, f"Create role '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        client.service.roles.create(name, **kwargs)
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Role '{name}' created.")


@roles_group.command("update")
@guard.guarded
@click.argument("name")
@click.option(
    "--capabilities",
    default=None,
    help="Comma-separated capabilities.",
)
@click.option(
    "--imported-roles",
    default=None,
    help="Comma-separated imported roles.",
)
@click.option(
    "--search-indexes",
    default=None,
    help="Comma-separated allowed indexes.",
)
@click.option("--search-filter", default=None, help="Search filter.")
@click.option("--default-app", default=None, help="Default app.")
@click.option("--set", "set_pairs", multiple=True, help="KEY=VALUE extra fields.")
@click.pass_context
def update_role(
    ctx: click.Context,
    name: str,
    capabilities: str | None,
    imported_roles: str | None,
    search_indexes: str | None,
    search_filter: str | None,
    default_app: str | None,
    set_pairs: tuple[str, ...],
) -> None:
    """Update an existing role."""
    kwargs: dict[str, Any] = {}
    if set_pairs:
        kwargs.update(parse_set(set_pairs))
    if capabilities:
        kwargs["capabilities"] = [c.strip() for c in capabilities.split(",")]
    if imported_roles:
        kwargs["imported_roles"] = [r.strip() for r in imported_roles.split(",")]
    if search_indexes:
        kwargs["srchIndexesAllowed"] = [i.strip() for i in search_indexes.split(",")]
    if search_filter:
        kwargs["srchFilter"] = search_filter
    if default_app:
        kwargs["defaultApp"] = default_app
    if not kwargs:
        output.error("No update fields specified.")
        ctx.exit(1)
        return
    details = f"  role: {name}"
    for k, v in kwargs.items():
        details += f"\n  {k}: {v}"
    if not guard.check(ctx, f"Update role '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        role = client.service.roles[name]
    except KeyError:
        output.error(f"Role '{name}' not found.")
        ctx.exit(1)
        return
    role.update(**kwargs)
    output.info(f"Role '{name}' updated.")


@roles_group.command("delete")
@guard.guarded
@click.argument("name")
@click.pass_context
def delete_role(ctx: click.Context, name: str) -> None:
    """Delete a role."""
    if not guard.check(ctx, f"Delete role '{name}'"):
        return
    client = get_client(ctx)
    try:
        role = client.service.roles[name]
    except KeyError:
        output.error(f"Role '{name}' not found.")
        ctx.exit(1)
        return
    role.delete()
    output.info(f"Role '{name}' deleted.")


# --- user CRUD ---


@users_group.command("create")
@guard.guarded
@click.option("--name", "username", required=True, help="Username.")
@click.option("--password", required=True, help="Password.")
@click.option(
    "--roles",
    required=True,
    help="Comma-separated role names.",
)
@click.option("--email", default=None, help="Email address.")
@click.option("--realname", default=None, help="Display name.")
@click.pass_context
def create_user(
    ctx: click.Context,
    username: str,
    password: str,
    roles: str,
    *,
    email: str | None,
    realname: str | None,
) -> None:
    """Create a new user."""
    roles_list = [r.strip() for r in roles.split(",")]
    details = f"Create user '{username}' with roles: {', '.join(roles_list)}"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    kwargs: dict[str, Any] = {"password": password, "roles": roles_list}
    if email:
        kwargs["email"] = email
    if realname:
        kwargs["realname"] = realname

    try:
        client.service.users.create(username, **kwargs)
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Created user '{username}'.")


@users_group.command("update")
@guard.guarded
@click.argument("name")
@click.option("--roles", default=None, help="Comma-separated role names.")
@click.option("--email", default=None, help="Email address.")
@click.option("--realname", default=None, help="Display name.")
@click.option("--default-app", default=None, help="Default app.")
@click.option("--password", default=None, help="New password.")
@click.option("--set", "set_pairs", multiple=True, help="KEY=VALUE extra fields.")
@click.pass_context
def update_user(
    ctx: click.Context,
    name: str,
    set_pairs: tuple[str, ...],
    *,
    roles: str | None,
    email: str | None,
    realname: str | None,
    default_app: str | None,
    password: str | None,
) -> None:
    """Update an existing user."""
    kwargs: dict[str, Any] = {}
    if set_pairs:
        kwargs.update(parse_set(set_pairs))
    if roles is not None:
        kwargs["roles"] = [r.strip() for r in roles.split(",")]
    if email is not None:
        kwargs["email"] = email
    if realname is not None:
        kwargs["realname"] = realname
    if default_app is not None:
        kwargs["defaultApp"] = default_app
    if password is not None:
        kwargs["password"] = password

    if not kwargs:
        output.error("No update fields specified.")
        ctx.exit(1)
        return

    show_kwargs = {k: ("***" if k == "password" else v) for k, v in kwargs.items()}
    changes = ", ".join(f"{k}={v}" for k, v in show_kwargs.items())
    if not guard.check(ctx, f"Update user '{name}'", details=changes):
        return

    client = get_client(ctx)
    try:
        user = client.service.users[name]
    except KeyError:
        output.error(f"User '{name}' not found.")
        ctx.exit(1)
        return

    try:
        user.update(**kwargs)
        user.refresh()
    except Exception as exc:
        output.error(f"Update failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Updated user '{name}'.")


@users_group.command("delete")
@guard.guarded
@click.argument("name")
@click.pass_context
def delete_user(ctx: click.Context, name: str) -> None:
    """Delete a user."""
    if not guard.check(ctx, f"Delete user '{name}'"):
        return

    client = get_client(ctx)
    try:
        user = client.service.users[name]
    except KeyError:
        output.error(f"User '{name}' not found.")
        ctx.exit(1)
        return

    try:
        user.delete()
    except Exception as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Deleted user '{name}'.")
