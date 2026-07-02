"""Dashboard management via SDK."""

from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client


@click.group("dashboards")
def dashboards_group() -> None:
    """Dashboard management."""


@dashboards_group.command("list")
@click.option("--app", default="-", help="Only dashboards owned by this app.")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include non-dashboard views (nav, forms marked isDashboard=0).",
)
@click.pass_context
def list_dashboards(ctx: click.Context, *, app: str, show_all: bool) -> None:
    """List dashboards."""
    client = get_client(ctx)
    items = client.service.dashboards.list(app=app, owner="-")
    rows: list[dict[str, Any]] = []
    for d in items:
        if app != "-" and d.access.app != app:
            continue
        is_dashboard = d.content.get("isDashboard", False)
        if not show_all and str(is_dashboard) in ("0", "False"):
            continue
        rows.append(
            {
                "name": d.name,
                "app": d.access.app,
                "owner": getattr(d.access, "owner", ""),
                "sharing": getattr(d.access, "sharing", ""),
                "label": d.content.get("label", ""),
                "isDashboard": is_dashboard,
                "isVisible": d.content.get("isVisible", False),
            }
        )
    output.render(ctx, rows, empty="No dashboards found.")


@dashboards_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.pass_context
def get_dashboard(ctx: click.Context, name: str, *, app: str) -> None:
    """Get dashboard details including XML source."""
    client = get_client(ctx)
    try:
        matches = client.service.dashboards.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        d = matches[0]
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    row: dict[str, Any] = {
        "name": d.name,
        "app": d.access.app,
        "label": d.content.get("label", ""),
        "isDashboard": d.content.get("isDashboard", False),
        "isVisible": d.content.get("isVisible", False),
        "eai:data": d.export(),
    }
    output.render(ctx, row)


@dashboards_group.command("create")
@click.option("--name", required=True, help="Dashboard name.")
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True),
    help="XML file path.",
)
@click.option("--app", default="search", help="Splunk app context.")
@click.pass_context
def create_dashboard(
    ctx: click.Context,
    name: str,
    filepath: str,
    *,
    app: str,
) -> None:
    """Create a dashboard from XML file."""
    xml_content = Path(filepath).read_text(encoding="utf-8")
    details = f"  name: {name}\n  app: {app}\n  file: {filepath}"
    if not guard.check(ctx, f"Create dashboard '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        client.service.dashboards.create(name, xml_content, app=app)
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Dashboard '{name}' created in app '{app}'.")


@dashboards_group.command("update")
@click.argument("name")
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True),
    help="XML file path.",
)
@click.option("--app", default="search", help="Splunk app context.")
@click.pass_context
def update_dashboard(
    ctx: click.Context,
    name: str,
    filepath: str,
    *,
    app: str,
) -> None:
    """Update dashboard XML."""
    xml_content = Path(filepath).read_text(encoding="utf-8")
    details = f"  name: {name}\n  app: {app}\n  file: {filepath}"
    if not guard.check(ctx, f"Update dashboard '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        matches = client.service.dashboards.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        matches[0].update(**{"eai:data": xml_content})
    except (KeyError, Exception) as exc:
        output.error(f"Update failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Dashboard '{name}' updated.")


@dashboards_group.command("delete")
@click.argument("name")
@click.option("--app", default="search", help="Splunk app context.")
@click.pass_context
def delete_dashboard(ctx: click.Context, name: str, *, app: str) -> None:
    """Delete a dashboard."""
    if not guard.check(ctx, f"Delete dashboard '{name}'", details=f"  app: {app}"):
        return
    client = get_client(ctx)
    try:
        matches = client.service.dashboards.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        matches[0].delete()
    except (KeyError, Exception) as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Dashboard '{name}' deleted.")


@dashboards_group.command("export")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.option(
    "--out",
    "out_file",
    type=click.Path(),
    default=None,
    help="Output file.",
)
@click.pass_context
def export_dashboard(
    ctx: click.Context, name: str, *, app: str, out_file: str | None
) -> None:
    """Export dashboard XML to file or stdout."""
    client = get_client(ctx)
    try:
        matches = client.service.dashboards.list(
            search=f"name={name}",
            app=app,
            owner="-",
            count=1,
        )
        if not matches:
            raise KeyError(name)
        xml = matches[0].export()
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    if out_file:
        Path(out_file).write_text(xml, encoding="utf-8")
        output.info(f"Exported to {out_file}")
    else:
        click.echo(xml)
