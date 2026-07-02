"""User and role management commands."""

from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client

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
@click.pass_context
def list_users(ctx: click.Context) -> None:
    """List all users."""
    client = get_client(ctx)
    users = client.service.users.list()
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


@users_group.command("roles")
@click.pass_context
def list_roles(ctx: click.Context) -> None:
    """List all roles."""
    client = get_client(ctx)
    roles = client.service.roles.list()
    truncate = output.is_table(ctx)
    rows = [_role_row(r, truncate=truncate) for r in roles]
    output.render(ctx, rows, empty="No roles found.")


@users_group.command("create")
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
@click.argument("name")
@click.option("--roles", default=None, help="Comma-separated role names.")
@click.option("--email", default=None, help="Email address.")
@click.option("--realname", default=None, help="Display name.")
@click.option("--default-app", default=None, help="Default app.")
@click.pass_context
def update_user(
    ctx: click.Context,
    name: str,
    *,
    roles: str | None,
    email: str | None,
    realname: str | None,
    default_app: str | None,
) -> None:
    """Update an existing user."""
    kwargs: dict[str, Any] = {}
    if roles is not None:
        kwargs["roles"] = [r.strip() for r in roles.split(",")]
    if email is not None:
        kwargs["email"] = email
    if realname is not None:
        kwargs["realname"] = realname
    if default_app is not None:
        kwargs["defaultApp"] = default_app

    if not kwargs:
        output.error("No update fields specified.")
        ctx.exit(1)
        return

    changes = ", ".join(f"{k}={v}" for k, v in kwargs.items())
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
