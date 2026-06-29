"""Dashboard CRUD — raw REST (SDK gap)."""

import json
import urllib.parse
from pathlib import Path
from typing import Any
from urllib.parse import quote

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_READ_BASE = "/servicesNS/-/{app}/data/ui/views"
_WRITE_BASE = "/servicesNS/nobody/{app}/data/ui/views"


def _read_path(app: str, name: str | None = None) -> str:
    base = _READ_BASE.format(app=quote(app, safe=""))
    return f"{base}/{quote(name, safe='')}" if name else base


def _write_path(app: str, name: str | None = None) -> str:
    base = _WRITE_BASE.format(app=quote(app, safe=""))
    return f"{base}/{quote(name, safe='')}" if name else base


def _rest_get(service: Any, path: str) -> dict[str, Any]:
    """GET JSON from Splunk REST API."""
    resp = service.get(path, output_mode="json", count=0)
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


@click.group("dashboards")
def dashboards_group() -> None:
    """Dashboard management (raw REST)."""


@dashboards_group.command("list")
@click.option("--app", default="-", help="Splunk app context.")
@click.pass_context
def list_dashboards(ctx: click.Context, *, app: str) -> None:
    """List dashboards."""
    client = get_client(ctx)
    body = _rest_get(client.service, _read_path(app))
    rows: list[dict[str, Any]] = [
        {
            "name": e["name"],
            "app": e.get("acl", {}).get("app", ""),
            "label": e.get("content", {}).get("label", ""),
            "isDashboard": e.get("content", {}).get("isDashboard", False),
            "isVisible": e.get("content", {}).get("isVisible", False),
        }
        for e in body.get("entry", [])
    ]
    output.render(ctx, rows)


@dashboards_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.pass_context
def get_dashboard(ctx: click.Context, name: str, *, app: str) -> None:
    """Get dashboard details including XML source."""
    client = get_client(ctx)
    try:
        body = _rest_get(client.service, _read_path(app, name))
    except Exception as exc:
        output.error(f"Dashboard '{name}' not found: {exc}")
        ctx.exit(1)
        return
    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    e = entries[0]
    row: dict[str, Any] = {
        "name": e["name"],
        "app": e.get("acl", {}).get("app", ""),
        "label": e.get("content", {}).get("label", ""),
        "isDashboard": e.get("content", {}).get("isDashboard", False),
        "isVisible": e.get("content", {}).get("isVisible", False),
        "eai:data": e.get("content", {}).get("eai:data", ""),
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
@click.option("--label", default=None, help="Dashboard label.")
@click.pass_context
def create_dashboard(
    ctx: click.Context,
    name: str,
    filepath: str,
    *,
    app: str,
    label: str | None,
) -> None:
    """Create a dashboard from XML file."""
    xml_content = Path(filepath).read_text(encoding="utf-8")
    details = f"  name: {name}\n  app: {app}\n  file: {filepath}"
    if label:
        details += f"\n  label: {label}"
    if not guard.check(ctx, f"Create dashboard '{name}'", details=details):
        return
    client = get_client(ctx)
    params: dict[str, str] = {"name": name, "eai:data": xml_content}
    if label:
        params["label"] = label
    try:
        client.service.post(_write_path(app), body=urllib.parse.urlencode(params))
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
        client.service.post(
            _write_path(app, name),
            body=urllib.parse.urlencode({"eai:data": xml_content}),
        )
    except Exception as exc:
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
        client.service.delete(_write_path(app, name))
    except Exception as exc:
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
        body = _rest_get(client.service, _read_path(app, name))
    except Exception as exc:
        output.error(f"Dashboard '{name}' not found: {exc}")
        ctx.exit(1)
        return
    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    xml: str = entries[0].get("content", {}).get("eai:data", "")
    if out_file:
        Path(out_file).write_text(xml, encoding="utf-8")
        output.info(f"Exported to {out_file}")
    else:
        click.echo(xml)
