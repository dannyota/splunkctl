"""Per-type pull/diff/apply adapters for `state` (Task I1: config-as-code).

Orchestrates the *existing* per-type read/diff/apply paths — never
re-implements serialization or apply logic. This module is the public
facade (``state.py`` and tests import everything through it): shared
types/helpers live in ``state_types.py``; parsers/macros adapters live
in ``state_io_confs.py``; lookups/dashboards adapters live in
``state_io_blobs.py`` (split to stay under the 500-line file budget —
each is re-exported here so ``state_io.<name>`` keeps working).

- rules: ``rules_io``'s own field-diff (``_rule_diff``) and apply
  (``_apply_rule``) helpers.
- parsers: ``parsers_io``'s explicit-key reader and apply
  (``_apply_stanza``) helpers.
- macros: the same explicit-key reader plus ``conf_ops.set_keys``.
- lookups: ``client.upload_lookup`` plus a oneshot ``| inputlookup`` read.
- dashboards: ``Dashboard.export()`` for pull/diff. **No apply path
  exists** — dashboards are pull+diff only, so ``APPLY_FNS`` has no
  "dashboards" entry; callers must not attempt to write them.

Drift classification is uniform across types: ``added`` (on-disk, not on
the instance — would be created), ``removed`` (on the instance, not on
disk — push never deletes), ``modified`` (differing fields/content),
``unchanged``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from splunkctl import __version__
from splunkctl.commands.rules_io import RuleDiff, _apply_rule, _rule_diff, _rule_to_dict
from splunkctl.commands.state_io_blobs import (
    apply_lookups,
    diff_dashboards,
    diff_lookups,
    pull_dashboards,
    pull_lookups,
)
from splunkctl.commands.state_io_confs import (
    apply_macros,
    apply_parsers,
    diff_macros,
    diff_parsers,
    pull_macros,
    pull_parsers,
)
from splunkctl.commands.state_types import (
    Change,
    _doc_app,
    _load_yaml_list,
    _write_yaml,
)
from splunkctl.commands.state_types import ChangeRecord as ChangeRecord
from splunkctl.commands.state_types import DriftEntry as DriftEntry
from splunkctl.commands.state_types import change_record as change_record

TYPES: tuple[str, ...] = ("rules", "parsers", "macros", "lookups", "dashboards")
# Types `state push` can actually apply -- dashboards is pull+diff only.
APPLICABLE_TYPES: tuple[str, ...] = ("rules", "parsers", "macros", "lookups")


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------

_RULE_CHANGE: dict[str, Change] = {
    "create": "added",
    "update": "modified",
    "unchanged": "unchanged",
    "exists": "unchanged",
}


def _rule_app(ss: Any) -> str:
    acl: dict[str, Any] = ss.access
    return str(acl.get("app", "search") or "search")


def _drift_from_rule_diff(rd: RuleDiff) -> DriftEntry:
    # rd["name"] is only None for kind == "skip", which every caller filters
    # out before reaching here (an invalid YAML doc has no name to report).
    name = rd["name"]
    if name is None:
        raise ValueError("cannot build a drift entry for a skipped (nameless) rule doc")
    entry: DriftEntry = {"name": name, "change": _RULE_CHANGE[rd["kind"]]}
    if rd["changes"]:
        entry["fields"] = rd["changes"]
    return entry


def pull_rules(client: Any, dir_path: Path, app: str | None) -> int:
    """Snapshot saved searches to ``<dir>/rules.yml`` (reuses ``_rule_to_dict``)."""
    svc = client.service
    docs = [
        _rule_to_dict(ss)
        for ss in svc.saved_searches.list()
        if app is None or _rule_app(ss) == app
    ]
    _write_yaml(dir_path / "rules.yml", docs)
    return len(docs)


def diff_rules(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Classify every on-disk rule plus any live rule missing from disk."""
    svc = client.service
    docs = _load_yaml_list(dir_path / "rules.yml")
    entries: list[DriftEntry] = []
    disk_names: set[str] = set()
    for doc in docs:
        if not doc.get("name") or (app is not None and _doc_app(doc) != app):
            continue
        disk_names.add(str(doc["name"]))
        rd = _rule_diff(svc, doc, update=True)
        if rd["kind"] == "skip":
            continue
        entries.append(_drift_from_rule_diff(rd))
    for ss in svc.saved_searches.list():
        if app is not None and _rule_app(ss) != app:
            continue
        if ss.name in disk_names:
            continue
        entries.append({"name": ss.name, "change": "removed"})
    return entries


def apply_rules(client: Any, dir_path: Path, app: str | None) -> list[ChangeRecord]:
    """Apply added/modified on-disk rules via ``rules_io._apply_rule``.

    Never touches a live rule absent from disk (push never deletes).
    """
    svc = client.service
    docs = _load_yaml_list(dir_path / "rules.yml")
    records: list[ChangeRecord] = []
    for doc in docs:
        if not doc.get("name") or (app is not None and _doc_app(doc) != app):
            continue
        rd = _rule_diff(svc, doc, update=True)
        if rd["kind"] not in ("create", "update"):
            continue
        _apply_rule(svc, doc, update=True)
        records.append(change_record("rules", _drift_from_rule_diff(rd)))
    return records


# --------------------------------------------------------------------------
# registry, manifest, report
# --------------------------------------------------------------------------

PULL_FNS: dict[str, Callable[[Any, Path, str | None], int]] = {
    "rules": pull_rules,
    "parsers": pull_parsers,
    "macros": pull_macros,
    "lookups": pull_lookups,
    "dashboards": pull_dashboards,
}

DIFF_FNS: dict[str, Callable[[Any, Path, str | None], list[DriftEntry]]] = {
    "rules": diff_rules,
    "parsers": diff_parsers,
    "macros": diff_macros,
    "lookups": diff_lookups,
    "dashboards": diff_dashboards,
}

# dashboards intentionally absent -- no import/apply path exists (brief SCOPE 1).
APPLY_FNS: dict[str, Callable[[Any, Path, str | None], list[ChangeRecord]]] = {
    "rules": apply_rules,
    "parsers": apply_parsers,
    "macros": apply_macros,
    "lookups": apply_lookups,
}


def resolve_host(client: Any) -> str:
    """``host:port`` label for the manifest/report — no wall-clock, ever."""
    svc = client.service
    return f"{svc.host}:{svc.port}"


def write_manifest(dir_path: Path, *, host: str, counts: dict[str, int]) -> None:
    """Write ``<dir>/manifest.json``: tool version, host, per-type object counts.

    Deliberately has no timestamp field — a wall-clock stamp would make
    the manifest, and any test asserting its content, non-deterministic.
    The pull's own version-control commit (or filesystem mtime) already
    carries a "when"; this file's job is "what" and "from where".
    """
    manifest = {"version": __version__, "host": host, "types": counts}
    (dir_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def write_report(
    path: Path,
    *,
    host: str,
    types: list[str],
    changes: list[ChangeRecord],
    applied: bool,
) -> None:
    """Write the change-ticket evidence artifact: before/after per applied change."""
    report = {"host": host, "types": types, "changes": changes, "applied": applied}
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
