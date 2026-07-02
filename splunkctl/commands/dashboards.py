"""Dashboard management via SDK."""

import difflib
import json as json_mod
from pathlib import Path
from typing import Any

import click
import defusedxml.ElementTree as ET

from splunkctl import guard, output
from splunkctl.client import get_client


def _detect_type(xml: str) -> str:
    try:
        root = ET.fromstring(xml)
        if root.get("version") == "2":
            return "studio"
    except ET.ParseError:
        pass
    return "classic"


def _validate(content: str, dash_type: str) -> str:
    if dash_type == "auto":
        dash_type = "studio" if content.lstrip().startswith("{") else "classic"
    if dash_type == "studio":
        try:
            json_mod.loads(content)
        except json_mod.JSONDecodeError as exc:
            raise click.BadParameter(
                f"Invalid JSON (line {exc.lineno} col {exc.colno}): {exc.msg}"
            ) from exc
        return content
    try:
        ET.fromstring(content)
    except ET.ParseError as exc:
        raise click.BadParameter(f"Invalid XML: {exc}") from exc
    return content


def _studio_wrap(name: str, json_content: str) -> str:
    return (
        '<dashboard version="2" theme="light">'
        f"<label>{name}</label>"
        f"<definition><![CDATA[{json_content}]]></definition>"
        "</dashboard>"
    )


def _extract_definition(xml: str) -> str | None:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    if root.get("version") != "2":
        return None
    defn = root.find("definition")
    if defn is None or not defn.text:
        return None
    try:
        parsed = json_mod.loads(defn.text)
        return json_mod.dumps(parsed, indent=2)
    except json_mod.JSONDecodeError:
        return str(defn.text)


def _resolve(svc: Any, name: str, app: str) -> Any:
    matches = svc.dashboards.list(
        search=f"name={name}",
        app=app,
        owner="-",
        count=1,
    )
    if not matches:
        raise KeyError(name)
    return matches[0]


def _diff_preview(
    old: str,
    new: str,
    max_lines: int = 40,
) -> str:
    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile="current",
            tofile="new",
            lineterm="",
        )
    )
    if not lines:
        return "  (no change)"
    shown = lines[:max_lines]
    text = "\n".join(f"  {line}" for line in shown)
    if len(lines) > max_lines:
        text += f"\n  ... (+{len(lines) - max_lines} more lines)"
    return text


@click.group("dashboards")
def dashboards_group() -> None:
    """Dashboard management."""


@dashboards_group.command("list")
@click.option("--app", default="-", help="Only dashboards owned by this app.")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include non-dashboard views.",
)
@click.pass_context
def list_dashboards(
    ctx: click.Context,
    *,
    app: str,
    show_all: bool,
) -> None:
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
        xml_data = str(d.content.get("eai:data", ""))
        rows.append(
            {
                "name": d.name,
                "app": d.access.app,
                "owner": getattr(d.access, "owner", ""),
                "sharing": getattr(d.access, "sharing", ""),
                "type": _detect_type(xml_data),
                "label": d.content.get("label", ""),
            }
        )
    output.render(ctx, rows, empty="No dashboards found.")


@dashboards_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.option(
    "--definition",
    is_flag=True,
    help="Extract Studio JSON definition (errors on classic).",
)
@click.pass_context
def get_dashboard(
    ctx: click.Context,
    name: str,
    *,
    app: str,
    definition: bool,
) -> None:
    """Get dashboard details including XML source."""
    client = get_client(ctx)
    try:
        d = _resolve(client.service, name, app)
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    xml = d.export()
    if definition:
        defn = _extract_definition(xml)
        if defn is None:
            output.error("Not a Studio dashboard (version!=2).")
            ctx.exit(1)
            return
        click.echo(defn)
        return
    row: dict[str, Any] = {
        "name": d.name,
        "app": d.access.app,
        "type": _detect_type(xml),
        "label": d.content.get("label", ""),
        "isDashboard": d.content.get("isDashboard", False),
        "isVisible": d.content.get("isVisible", False),
        "eai:data": xml,
    }
    output.render(ctx, row)


_TYPE_CHOICE = click.Choice(["classic", "studio", "auto"])


@dashboards_group.command("create")
@guard.guarded
@click.option("--name", required=True, help="Dashboard name.")
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True),
    help="XML or JSON file.",
)
@click.option("--app", default="search", help="Splunk app context.")
@click.option("--type", "dash_type", type=_TYPE_CHOICE, default="auto")
@click.option(
    "--sharing",
    type=click.Choice(["user", "app", "global"]),
    default=None,
    help="Set sharing level after creation.",
)
@click.pass_context
def create_dashboard(
    ctx: click.Context,
    name: str,
    filepath: str,
    *,
    app: str,
    dash_type: str,
    sharing: str | None,
) -> None:
    """Create a dashboard from an XML or JSON file."""
    content = Path(filepath).read_text(encoding="utf-8")
    try:
        _validate(content, dash_type)
    except click.BadParameter as exc:
        output.error(str(exc))
        ctx.exit(1)
        return
    resolved = dash_type
    if resolved == "auto":
        resolved = "studio" if content.lstrip().startswith("{") else "classic"
    if resolved == "studio":
        content = _studio_wrap(name, content)
    details = f"  name: {name}\n  app: {app}\n  type: {resolved}"
    if sharing:
        details += f"\n  sharing: {sharing}"
    if not guard.check(ctx, f"Create dashboard '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        entity = client.service.dashboards.create(
            name,
            content,
            app=app,
        )
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    if sharing:
        client.set_acl(entity, sharing=sharing)
    output.info(f"Dashboard '{name}' created in app '{app}'.")


@dashboards_group.command("update")
@guard.guarded
@click.argument("name")
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True),
    help="XML or JSON file.",
)
@click.option("--app", default="search", help="Splunk app context.")
@click.option("--type", "dash_type", type=_TYPE_CHOICE, default="auto")
@click.pass_context
def update_dashboard(
    ctx: click.Context,
    name: str,
    filepath: str,
    *,
    app: str,
    dash_type: str,
) -> None:
    """Update dashboard XML."""
    new_content = Path(filepath).read_text(encoding="utf-8")
    try:
        _validate(new_content, dash_type)
    except click.BadParameter as exc:
        output.error(str(exc))
        ctx.exit(1)
        return
    resolved = dash_type
    if resolved == "auto":
        resolved = "studio" if new_content.lstrip().startswith("{") else "classic"
    if resolved == "studio":
        new_content = _studio_wrap(name, new_content)
    client = get_client(ctx)
    try:
        d = _resolve(client.service, name, app)
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    cur_xml = d.export()
    diff = _diff_preview(cur_xml, new_content)
    details = f"  name: {name}\n  app: {app}\n  type: {resolved}\n{diff}"
    if not guard.check(ctx, f"Update dashboard '{name}'", details=details):
        return
    d.update(**{"eai:data": new_content})
    output.info(f"Dashboard '{name}' updated.")


@dashboards_group.command("delete")
@guard.guarded
@click.argument("name")
@click.option("--app", default="search", help="Splunk app context.")
@click.pass_context
def delete_dashboard(ctx: click.Context, name: str, *, app: str) -> None:
    """Delete a dashboard."""
    if not guard.check(
        ctx,
        f"Delete dashboard '{name}'",
        details=f"  app: {app}",
    ):
        return
    client = get_client(ctx)
    try:
        d = _resolve(client.service, name, app)
    except (KeyError, Exception) as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    d.delete()
    output.info(f"Dashboard '{name}' deleted.")


@dashboards_group.command("export")
@click.argument("name", required=False, default=None)
@click.option("--app", default="-", help="Splunk app context.")
@click.option(
    "--out",
    "out_file",
    type=click.Path(),
    default=None,
    help="Output file (single dashboard).",
)
@click.option(
    "--definition",
    is_flag=True,
    help="Extract Studio JSON definition.",
)
@click.option(
    "--all",
    "export_all",
    is_flag=True,
    help="Export all dashboards to --dir.",
)
@click.option(
    "--dir",
    "out_dir",
    type=click.Path(),
    default=None,
    help="Directory for --all bulk export.",
)
@click.pass_context
def export_dashboard(
    ctx: click.Context,
    name: str | None,
    *,
    app: str,
    out_file: str | None,
    definition: bool,
    export_all: bool,
    out_dir: str | None,
) -> None:
    """Export dashboard XML to file or stdout."""
    if export_all:
        _export_all(ctx, app=app, out_dir=out_dir)
        return
    if not name:
        output.error("Provide a dashboard NAME or use --all --dir DIR.")
        ctx.exit(1)
        return
    client = get_client(ctx)
    try:
        d = _resolve(client.service, name, app)
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    xml = d.export()
    if definition:
        defn = _extract_definition(xml)
        if defn is None:
            output.error("Not a Studio dashboard (version!=2).")
            ctx.exit(1)
            return
        if out_file:
            Path(out_file).write_text(defn, encoding="utf-8")
            output.info(f"Exported definition to {out_file}")
        else:
            click.echo(defn)
        return
    if out_file:
        Path(out_file).write_text(xml, encoding="utf-8")
        output.info(f"Exported to {out_file}")
    else:
        click.echo(xml)


def _export_all(ctx: click.Context, *, app: str, out_dir: str | None) -> None:
    if not out_dir:
        output.error("--all requires --dir DIR.")
        ctx.exit(1)
        return
    client = get_client(ctx)
    items = client.service.dashboards.list(app=app, owner="-")
    base = Path(out_dir)
    count = 0
    for d in items:
        is_dash = d.content.get("isDashboard", False)
        if str(is_dash) in ("0", "False"):
            continue
        d_app = d.access.app
        if app != "-" and d_app != app:
            continue
        app_dir = base / d_app
        app_dir.mkdir(parents=True, exist_ok=True)
        xml = d.export()
        (app_dir / f"{d.name}.xml").write_text(xml, encoding="utf-8")
        count += 1
    output.info(f"Exported {count} dashboard(s) to {out_dir}/.")


@dashboards_group.command("share")
@guard.guarded
@click.argument("name")
@click.option(
    "--sharing",
    required=True,
    type=click.Choice(["user", "app", "global"]),
)
@click.option("--owner", default=None, help="New owner.")
@click.option("--app", default="search", help="Splunk app context.")
@click.pass_context
def share_dashboard(
    ctx: click.Context,
    name: str,
    sharing: str,
    owner: str | None,
    *,
    app: str,
) -> None:
    """Change dashboard sharing level."""
    details = f"  name: {name}\n  sharing: {sharing}"
    if owner:
        details += f"\n  owner: {owner}"
    if not guard.check(
        ctx,
        f"Share dashboard '{name}'",
        details=details,
    ):
        return
    client = get_client(ctx)
    try:
        d = _resolve(client.service, name, app)
    except (KeyError, Exception):
        output.error(f"Dashboard '{name}' not found.")
        ctx.exit(1)
        return
    client.set_acl(d, sharing=sharing, owner=owner)
    output.info(f"Dashboard '{name}' sharing set to '{sharing}'.")
