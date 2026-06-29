"""App management commands — list, get, install, uninstall, update, reload."""

from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_APP_FIELDS = ("label", "version", "visible", "disabled", "author", "description")


def _app_row(app: Any) -> dict[str, Any]:
    content: dict[str, Any] = dict(app.content)
    return {
        "name": app.name,
        **{f: content.get(f, "") for f in _APP_FIELDS},
    }


def _list_fields(app: Any) -> dict[str, Any]:
    content: dict[str, Any] = dict(app.content)
    return {
        "name": app.name,
        "label": content.get("label", ""),
        "version": content.get("version", ""),
        "visible": content.get("visible", ""),
        "disabled": content.get("disabled", ""),
        "author": content.get("author", ""),
    }


@click.group("apps")
def apps_group() -> None:
    """Manage Splunk apps."""


@apps_group.command("list")
@click.pass_context
def list_apps(ctx: click.Context) -> None:
    """List installed apps."""
    client = get_client(ctx)
    svc = client.service
    apps = svc.apps.list()
    if not apps:
        output.info("No apps found.")
        return
    rows = [_list_fields(a) for a in apps]
    output.render(ctx, rows)


@apps_group.command("get")
@click.argument("name")
@click.pass_context
def get_app(ctx: click.Context, name: str) -> None:
    """Get app details."""
    client = get_client(ctx)
    svc = client.service
    try:
        app = svc.apps[name]
    except KeyError:
        output.error(f"App '{name}' not found.")
        ctx.exit(1)
        return
    output.render(ctx, _app_row(app))


@apps_group.command("install")
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to .tar.gz or .spl package.",
)
@click.option("--force", is_flag=True, help="Overwrite if app already exists.")
@click.pass_context
def install_app(ctx: click.Context, file_path: str, *, force: bool) -> None:
    """Install an app from a local .tar.gz or .spl file.

    Uploads via Splunk Web UI — works from a remote client without
    SSH access to the server.
    """
    p = Path(file_path)
    details = f"Install app from '{p.name}'"
    if force:
        details += " (force overwrite)"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    try:
        client.install_app(p, force=force)
    except Exception as exc:
        output.error(f"Install failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Installed app from '{p.name}'.")


@apps_group.command("uninstall")
@click.argument("name")
@click.pass_context
def uninstall_app(ctx: click.Context, name: str) -> None:
    """Uninstall an app."""
    details = f"Uninstall app '{name}'"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service
    try:
        app = svc.apps[name]
        app.delete()
    except KeyError:
        output.error(f"App '{name}' not found.")
        ctx.exit(1)
        return
    except Exception as exc:
        output.error(f"Uninstall failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Uninstalled app '{name}'.")


@apps_group.command("update")
@click.argument("name")
@click.option("--visible/--hidden", default=None, help="Set app visibility.")
@click.option("--enabled/--disabled", default=None, help="Enable or disable the app.")
@click.pass_context
def update_app(
    ctx: click.Context,
    name: str,
    visible: bool | None,
    enabled: bool | None,
) -> None:
    """Update app settings."""
    kwargs: dict[str, Any] = {}
    if visible is not None:
        kwargs["visible"] = visible
    if enabled is not None:
        kwargs["disabled"] = not enabled
    if not kwargs:
        msg = "No settings specified. Use --visible/--hidden or --enabled/--disabled."
        output.error(msg)
        ctx.exit(1)
        return

    parts: list[str] = []
    if visible is not None:
        parts.append(f"visible={'true' if visible else 'false'}")
    if enabled is not None:
        parts.append(f"disabled={'false' if enabled else 'true'}")
    details = f"Update app '{name}': {', '.join(parts)}"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service
    try:
        app = svc.apps[name]
        app.update(**kwargs)
    except KeyError:
        output.error(f"App '{name}' not found.")
        ctx.exit(1)
        return
    except Exception as exc:
        output.error(f"Update failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Updated app '{name}'.")


@apps_group.command("reload")
@click.pass_context
def reload_apps(ctx: click.Context) -> None:
    """Reload all apps."""
    if not guard.check(ctx, "Reload all apps"):
        return

    client = get_client(ctx)
    svc = client.service
    try:
        svc.get("/services/apps/local/_reload")
    except Exception as exc:
        output.error(f"Reload failed: {exc}")
        ctx.exit(1)
        return
    output.info("Apps reloaded.")
