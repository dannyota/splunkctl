"""Detection-as-code — import/export saved searches as YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import yaml

from splunkctl import guard, output
from splunkctl.client import get_client

_EXPORT_FIELDS = (
    "search",
    "description",
    "cron_schedule",
    "is_scheduled",
    "disabled",
    "actions",
    "alert_type",
    "alert.severity",
    "alert.suppress",
    "alert.suppress.period",
    "alert.suppress.fields",
    "alert.track",
    "dispatch.earliest_time",
    "dispatch.latest_time",
)


def _rule_to_dict(ss: Any) -> dict[str, Any]:
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    d: dict[str, Any] = {"name": ss.name}
    app = acl.get("app", "")
    if app and app != "search":
        d["app"] = app
    for f in _EXPORT_FIELDS:
        val = c.get(f, "")
        if val not in ("", None, "0", 0) or f == "search":
            d[f] = val
    return d


@click.command("export")
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output YAML file.",
)
@click.option("--name", multiple=True, help="Export specific rules (repeatable).")
@click.option("--app", default=None, help="Filter by app context.")
@click.pass_context
def export_rules(
    ctx: click.Context,
    file_path: str,
    name: tuple[str, ...],
    app: str | None,
) -> None:
    """Export saved searches to a YAML file."""
    client = get_client(ctx)
    svc = client.service

    if name:
        rules = []
        for n in name:
            try:
                rules.append(svc.saved_searches[n])
            except KeyError:
                output.error(f"Saved search not found: {n}")
                ctx.exit(1)
                return
    else:
        rules = svc.saved_searches.list()

    docs = []
    for ss in rules:
        d = _rule_to_dict(ss)
        if app and d.get("app", "search") != app:
            continue
        docs.append(d)

    if not docs:
        output.info("No rules to export.")
        return

    p = Path(file_path)
    p.write_text(
        yaml.dump(docs, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    output.info(f"Exported {len(docs)} rule(s) to {p.name}.")


def _apply_rule(
    svc: Any,
    rule: dict[str, Any],
    *,
    update: bool,
) -> str:
    name = rule["name"]
    spl = rule.get("search", "")
    if not spl:
        return f"skip:{name} (no search field)"

    kwargs: dict[str, Any] = {}
    for key in _EXPORT_FIELDS:
        if key == "search":
            continue
        if key in rule:
            kwargs[key] = rule[key]
    if kwargs.get("cron_schedule"):
        kwargs.setdefault("is_scheduled", "1")

    app = rule.get("app")

    try:
        ss = svc.saved_searches[name]
        if not update:
            return f"exists:{name}"
        ss.update(search=spl, **kwargs).refresh()
        return f"updated:{name}"
    except KeyError:
        create_kw: dict[str, Any] = {"search": spl, **kwargs}
        if app:
            create_kw["app"] = app
        svc.saved_searches.create(name, **create_kw)
        return f"created:{name}"


@click.command("import")
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="YAML file with rule definitions.",
)
@click.option(
    "--update/--no-update",
    default=True,
    help="Update existing rules (default: yes).",
)
@click.pass_context
def import_rules(
    ctx: click.Context,
    file_path: str,
    *,
    update: bool,
) -> None:
    """Import saved searches from a YAML file.

    Creates new rules and optionally updates existing ones.
    Dry-run by default — pass --yes to apply.
    """
    p = Path(file_path)
    try:
        docs = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        output.error(f"Invalid YAML: {exc}")
        ctx.exit(1)
        return

    if not isinstance(docs, list):
        output.error("YAML must be a list of rule objects.")
        ctx.exit(1)
        return

    names = [d.get("name", "?") for d in docs]
    detail = f"  rules: {', '.join(names[:5])}"
    if len(names) > 5:
        detail += f" (+{len(names) - 5} more)"
    detail += f"\n  update existing: {update}"

    if not guard.check(
        ctx,
        f"Import {len(docs)} rule(s) from {p.name}",
        details=detail,
    ):
        return

    client = get_client(ctx)
    svc = client.service

    results: list[str] = []
    for rule in docs:
        if not isinstance(rule, dict) or "name" not in rule:
            results.append("skip:invalid entry")
            continue
        try:
            results.append(_apply_rule(svc, rule, update=update))
        except Exception as exc:
            results.append(f"error:{rule.get('name', '?')}: {exc}")

    created = sum(1 for r in results if r.startswith("created:"))
    updated = sum(1 for r in results if r.startswith("updated:"))
    skipped = sum(1 for r in results if r.startswith("skip:"))
    existed = sum(1 for r in results if r.startswith("exists:"))
    errors = sum(1 for r in results if r.startswith("error:"))

    parts = []
    if created:
        parts.append(f"{created} created")
    if updated:
        parts.append(f"{updated} updated")
    if existed:
        parts.append(f"{existed} unchanged")
    if skipped:
        parts.append(f"{skipped} skipped")
    if errors:
        parts.append(f"{errors} failed")
    output.info(f"Import complete: {', '.join(parts)}.")

    for r in results:
        if r.startswith("error:"):
            output.error(r)

    if errors:
        ctx.exit(1)
