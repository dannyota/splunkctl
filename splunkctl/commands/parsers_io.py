"""Parsers-as-code — props/transforms stanzas as YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import click
import yaml

from splunkctl import guard, output
from splunkctl.client import get_client

_CONFS = ("props", "transforms")


def _explicit_keys(
    svc: Any, conf_name: str, stanza: str, app: str
) -> dict[str, Any] | None:
    """Explicitly set keys of a conf stanza via the configs endpoint."""
    path = (
        f"/servicesNS/nobody/{quote(app, safe='')}"
        f"/configs/conf-{conf_name}/{quote(stanza, safe='')}"
    )
    try:
        resp = svc.get(path, output_mode="json")
    except Exception:
        return None
    body = json.loads(resp.body.read())
    content: dict[str, Any] = body["entry"][0]["content"]
    return {
        k: v
        for k, v in content.items()
        if not k.startswith("eai:") and k != "disabled" and v not in ("", None)
    }


@click.command("export")
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output YAML file.",
)
@click.option(
    "--conf",
    "conf_name",
    type=click.Choice(["props", "transforms", "all"]),
    default="all",
    help="Which conf to export (default all).",
)
@click.option(
    "--filter",
    "name_filter",
    default=None,
    help="Case-insensitive stanza name substring filter.",
)
@click.pass_context
def export_parsers(
    ctx: click.Context,
    file_path: str,
    conf_name: str,
    name_filter: str | None,
) -> None:
    """Export props/transforms stanzas (explicit keys only) to YAML."""
    client = get_client(ctx)
    svc = client.service

    confs = list(_CONFS) if conf_name == "all" else [conf_name]
    docs: list[dict[str, Any]] = []
    needle = name_filter.lower() if name_filter else None
    for cf in confs:
        for stanza in svc.confs[cf].list():
            if needle and needle not in stanza.name.lower():
                continue
            acl: dict[str, Any] = dict(stanza.access)
            app = acl.get("app", "search") or "search"
            keys = _explicit_keys(svc, cf, stanza.name, app)
            if not keys:
                continue
            docs.append(
                {
                    "conf": cf,
                    "stanza": stanza.name,
                    "app": app,
                    "sharing": acl.get("sharing", ""),
                    "keys": keys,
                }
            )

    if not docs:
        output.info("No stanzas with explicit keys to export.")
        return

    p = Path(file_path)
    p.write_text(
        yaml.dump(docs, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    output.info(f"Exported {len(docs)} stanza(s) to {p.name}.")


def _plan_stanza(svc: Any, doc: Any) -> tuple[str, list[str]]:
    """Classify one YAML doc: (status line, per-key diff lines)."""
    if not isinstance(doc, dict) or not doc.get("stanza"):
        return "skip:invalid entry: no stanza", []
    name = str(doc["stanza"])
    conf_name = str(doc.get("conf", "props"))
    if conf_name not in _CONFS:
        return f"skip:{name}: unknown conf '{conf_name}'", []
    keys = doc.get("keys") or {}
    if not isinstance(keys, dict) or not keys:
        return f"skip:{name}: no keys", []
    try:
        stanza = svc.confs[conf_name][name]
    except KeyError:
        return f"create:{name}", []
    content: dict[str, Any] = stanza.content
    diff = [
        f"  {k}: {content.get(k, '')} -> {v}"
        for k, v in keys.items()
        if str(content.get(k, "")) != str(v)
    ]
    if not diff:
        return f"unchanged:{name}", []
    return f"update:{name}", diff


def _apply_stanza(client: Any, doc: dict[str, Any]) -> str:
    name = str(doc["stanza"])
    conf_name = str(doc.get("conf", "props"))
    keys: dict[str, Any] = {k: str(v) for k, v in (doc.get("keys") or {}).items()}
    sharing = doc.get("sharing") or None
    conf = client.service.confs[conf_name]
    try:
        stanza = conf[name]
    except KeyError:
        created = conf.create(name, **keys)
        client.set_acl(created, sharing=str(sharing or "app"))
        return f"created:{name}"
    content: dict[str, Any] = stanza.content
    if all(str(content.get(k, "")) == v for k, v in keys.items()):
        return f"unchanged:{name}"
    stanza.update(**keys)
    if sharing and dict(stanza.access).get("sharing") != sharing:
        client.set_acl(stanza, sharing=str(sharing))
    return f"updated:{name}"


@click.command("import")
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="YAML file with stanza definitions.",
)
@click.pass_context
def import_parsers(ctx: click.Context, file_path: str) -> None:
    """Import props/transforms stanzas from YAML.

    Dry-run previews create/update/unchanged per stanza with key-level
    diffs; exits non-zero when any stanza is skipped or fails. Reload
    with `parsers reload` afterwards for index-time keys.
    """
    p = Path(file_path)
    try:
        docs = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        output.error(f"Invalid YAML: {exc}")
        ctx.exit(1)
        return
    if not isinstance(docs, list):
        output.error("YAML must be a list of stanza objects.")
        ctx.exit(1)
        return

    client = get_client(ctx)
    svc = client.service

    plan_lines: list[str] = []
    for doc in docs:
        status, diff_lines = _plan_stanza(svc, doc)
        kind, _, label = status.partition(":")
        plan_lines.append(f"  {kind}: {label}")
        plan_lines.extend(f"  {line}" for line in diff_lines)
    detail = "\n".join(plan_lines)

    if not guard.check(
        ctx, f"Import {len(docs)} parser stanza(s) from {p.name}", details=detail
    ):
        return

    results: list[str] = []
    for doc in docs:
        status, _ = _plan_stanza(svc, doc)
        if status.startswith("skip:"):
            results.append(status)
            continue
        try:
            results.append(_apply_stanza(client, doc))
        except Exception as exc:
            results.append(f"error:{doc.get('stanza', '?')}: {exc}")

    counts: dict[str, int] = {}
    for r in results:
        kind = r.partition(":")[0]
        counts[kind] = counts.get(kind, 0) + 1
    parts = [
        f"{n} {kind}"
        for kind, n in counts.items()
        if kind in ("created", "updated", "unchanged")
    ]
    if counts.get("skip"):
        parts.append(f"{counts['skip']} skipped")
    if counts.get("error"):
        parts.append(f"{counts['error']} failed")
    output.info(f"Import complete: {', '.join(parts)}.")

    for r in results:
        if r.startswith(("skip:", "error:")):
            output.error(r)
    if counts.get("skip") or counts.get("error"):
        ctx.exit(1)
