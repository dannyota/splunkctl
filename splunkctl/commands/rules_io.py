"""Detection-as-code — import/export saved searches as YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NotRequired, TypedDict

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
    "alert_comparator",
    "alert_threshold",
    "alert_condition",
    "alert.severity",
    "alert.suppress",
    "alert.suppress.period",
    "alert.suppress.fields",
    "alert.track",
    "alert.digest_mode",
    "alert.expires",
    "dispatch.earliest_time",
    "dispatch.latest_time",
    "schedule_window",
    "realtime_schedule",
)

# server-computed / read-only keys that must never round-trip
_READONLY_PREFIXES = ("eai:", "embed.", "display.")
_READONLY_KEYS = frozenset(
    {
        "name",
        "app",
        "next_scheduled_time",
        "qualifiedSearch",
        "triggered_alert_count",
    }
)

_TRUNC = 60


def _trunc(val: str) -> str:
    """Truncate for the text preview, with an explicit hidden-length marker.

    Never emits a bare ``…`` — a truncated value always says how many
    characters were hidden, e.g. ``foo… [+57 chars]``.
    """
    if len(val) <= _TRUNC:
        return val
    kept = val[: _TRUNC - 1]
    hidden = len(val) - len(kept)
    return f"{kept}… [+{hidden} chars]"


class FieldChange(TypedDict):
    """One field's before/after value in a rule diff."""

    field: str
    old: str | None
    new: str


class RuleDiff(TypedDict):
    """Full, untruncated diff classification for one YAML rule doc.

    ``kind`` is the granular text-preview classification (create / update /
    unchanged / exists / skip). JSON output collapses ``exists`` into
    ``unchanged`` — see ``_json_row``.
    """

    name: str | None
    kind: str
    changes: list[FieldChange]
    reason: NotRequired[str]


def _rule_to_dict(ss: Any) -> dict[str, Any]:
    c: dict[str, Any] = ss.content
    acl: dict[str, Any] = ss.access
    d: dict[str, Any] = {"name": ss.name}
    app = acl.get("app", "")
    if app and app != "search":
        d["app"] = app
    for f in _EXPORT_FIELDS:
        val = c.get(f, "")
        if val not in ("", None) or f == "search":
            d[f] = val
    # parameters of enabled actions (action.email.to, action.webhook.param.url…)
    actions = str(c.get("actions", "") or "")
    for act in (a.strip() for a in actions.split(",") if a.strip()):
        prefix = f"action.{act}."
        for key, val in c.items():
            if key.startswith(prefix) and val not in ("", None):
                d[key] = val
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


def _import_kwargs(rule: dict[str, Any]) -> dict[str, Any]:
    """All YAML fields that go to the server, minus computed/readonly ones."""
    kwargs: dict[str, Any] = {}
    for key, val in rule.items():
        if key in _READONLY_KEYS or key == "search":
            continue
        if any(key.startswith(pfx) for pfx in _READONLY_PREFIXES):
            continue
        kwargs[key] = val
    if kwargs.get("cron_schedule"):
        kwargs.setdefault("is_scheduled", "1")
    return kwargs


def _changes(ss: Any, spl: str, kwargs: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Fields whose live value differs from the YAML value."""
    c: dict[str, Any] = ss.content
    diff: dict[str, tuple[str, str]] = {}
    if str(c.get("search", "")) != str(spl):
        diff["search"] = (str(c.get("search", "")), str(spl))
    for key, val in kwargs.items():
        cur = str(c.get(key, ""))
        if cur != str(val):
            diff[key] = (cur, str(val))
    return diff


def _field_changes(diff: dict[str, tuple[str, str]]) -> list[FieldChange]:
    return [{"field": k, "old": old, "new": new} for k, (old, new) in diff.items()]


def _create_changes(spl: str, kwargs: dict[str, Any]) -> list[FieldChange]:
    """Full set of fields a new rule would be created with (old is None)."""
    changes: list[FieldChange] = [{"field": "search", "old": None, "new": str(spl)}]
    changes.extend({"field": k, "old": None, "new": str(v)} for k, v in kwargs.items())
    return changes


def _rule_diff(svc: Any, rule: Any, *, update: bool) -> RuleDiff:
    """Classify one YAML doc and compute its full, untruncated field diff.

    This is the dry-run-only counterpart to ``_plan_rule`` (which drives
    the ``--yes`` apply path and is left untouched): a single pass that
    feeds both the text preview and the structured JSON diff.
    """
    if not isinstance(rule, dict) or "name" not in rule:
        return {
            "name": None,
            "kind": "skip",
            "changes": [],
            "reason": "invalid entry: no name",
        }
    name = rule["name"]
    spl = rule.get("search", "")
    if not spl:
        return {
            "name": name,
            "kind": "skip",
            "changes": [],
            "reason": "no search field",
        }
    kwargs = _import_kwargs(rule)
    try:
        ss = svc.saved_searches[name]
    except KeyError:
        return {"name": name, "kind": "create", "changes": _create_changes(spl, kwargs)}
    if not update:
        return {"name": name, "kind": "exists", "changes": []}
    diff = _changes(ss, spl, kwargs)
    if not diff:
        return {"name": name, "kind": "unchanged", "changes": []}
    return {"name": name, "kind": "update", "changes": _field_changes(diff)}


def _preview_lines(d: RuleDiff) -> list[str]:
    """Render one rule's diff as the human-readable text preview lines."""
    name = d["name"] or ""
    kind = d["kind"]
    if kind == "skip":
        reason = d.get("reason", "")
        label = f"{name}: {reason}" if name else reason
        return [f"  skip: {label}"]
    if kind == "update":
        lines = [f"  update: {name}"]
        lines.extend(
            f"    {c['field']}: {_trunc(str(c['old']))} -> {_trunc(c['new'])}"
            for c in d["changes"]
        )
        return lines
    return [f"  {kind}: {name}"]


# no-update-mode "exists" is reported to JSON consumers as "unchanged" — it
# matches the CLI's own summary counts, which already fold the two together.
_JSON_ACTIONS = {
    "create": "create",
    "update": "update",
    "unchanged": "unchanged",
    "exists": "unchanged",
    "skip": "skip",
}


def _json_row(d: RuleDiff) -> dict[str, Any]:
    """Build one rule's JSON diff row: ``{name, action, changes[, reason]}``."""
    row: dict[str, Any] = {
        "name": d["name"],
        "action": _JSON_ACTIONS[d["kind"]],
        "changes": d["changes"],
    }
    if d["kind"] == "skip":
        row["reason"] = d.get("reason", "")
    return row


def _plan_rule(svc: Any, rule: Any, *, update: bool) -> tuple[str, list[str]]:
    """Classify one YAML doc: (status line, per-field diff lines)."""
    if not isinstance(rule, dict) or "name" not in rule:
        return "skip:invalid entry: no name", []
    name = rule["name"]
    spl = rule.get("search", "")
    if not spl:
        return f"skip:{name}: no search field", []
    kwargs = _import_kwargs(rule)
    try:
        ss = svc.saved_searches[name]
    except KeyError:
        return f"create:{name}", []
    if not update:
        return f"exists:{name}", []
    diff = _changes(ss, spl, kwargs)
    if not diff:
        return f"unchanged:{name}", []
    lines = [f"  {k}: {_trunc(old)} -> {_trunc(new)}" for k, (old, new) in diff.items()]
    return f"update:{name}", lines


def _apply_rule(svc: Any, rule: dict[str, Any], *, update: bool) -> str:
    name = rule["name"]
    spl = rule.get("search", "")
    kwargs = _import_kwargs(rule)
    app = rule.get("app")

    try:
        ss = svc.saved_searches[name]
    except KeyError:
        create_kw: dict[str, Any] = {"search": spl, **kwargs}
        if app:
            create_kw["app"] = app
        svc.saved_searches.create(name, **create_kw)
        return f"created:{name}"
    if not update:
        return f"exists:{name}"
    if not _changes(ss, spl, kwargs):
        return f"unchanged:{name}"
    ss.update(search=spl, **kwargs).refresh()
    return f"updated:{name}"


@click.command("import")
@guard.guarded
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

    Dry-run previews create/update/unchanged per rule with field-level
    diffs on stderr. Pass ``--json``/``--format json`` to also get a
    full, untruncated JSON diff array on stdout: one object per rule,
    ``{"name", "action", "changes": [{"field", "old", "new"}]}`` — ``old``
    is null for ``create``, ``changes`` is empty for ``unchanged``.
    Exits non-zero when any rule is skipped or fails, so CI pipelines
    cannot silently pass a broken detections file.
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

    client = get_client(ctx)
    svc = client.service

    diffs = [_rule_diff(svc, rule, update=update) for rule in docs]
    plan_lines: list[str] = []
    for d in diffs:
        plan_lines.extend(_preview_lines(d))
    detail = f"  update existing: {update}\n" + "\n".join(plan_lines)

    if not guard.check(
        ctx,
        f"Import {len(docs)} rule(s) from {p.name}",
        details=detail,
    ):
        obj: dict[str, Any] = ctx.obj or {}
        if obj.get("json") or obj.get("format") == "json":
            output.render(ctx, [_json_row(d) for d in diffs])
        return

    results: list[str] = []
    for rule in docs:
        status, _ = _plan_rule(svc, rule, update=update)
        if status.startswith("skip:"):
            results.append(status)
            continue
        try:
            results.append(_apply_rule(svc, rule, update=update))
        except Exception as exc:
            results.append(f"error:{rule.get('name', '?')}: {exc}")

    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "exists": 0,
        "skip": 0,
        "error": 0,
    }
    for r in results:
        counts[r.partition(":")[0]] += 1

    parts = []
    if counts["created"]:
        parts.append(f"{counts['created']} created")
    if counts["updated"]:
        parts.append(f"{counts['updated']} updated")
    if counts["unchanged"] + counts["exists"]:
        parts.append(f"{counts['unchanged'] + counts['exists']} unchanged")
    if counts["skip"]:
        parts.append(f"{counts['skip']} skipped")
    if counts["error"]:
        parts.append(f"{counts['error']} failed")
    output.info(f"Import complete: {', '.join(parts)}.")

    for r in results:
        if r.startswith(("skip:", "error:")):
            output.error(r)

    if counts["skip"] or counts["error"]:
        ctx.exit(1)
