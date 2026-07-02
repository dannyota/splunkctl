"""Shared types and generic drift/diff helpers for the `state` group.

Pure, dependency-free building blocks shared by ``state_io.py`` (rules,
registry, manifest/report) and its per-topic siblings
``state_io_confs.py`` (parsers/macros) and ``state_io_blobs.py``
(lookups/dashboards) — kept in one place so all four object types report
drift through the exact same classification and report shape.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

import yaml

Change = Literal["added", "removed", "modified", "unchanged"]


class FieldChange(TypedDict):
    """One field's before/after value in a structured drift entry."""

    field: str
    old: str | None
    new: str


class DriftEntry(TypedDict):
    """One object's drift classification within a single type."""

    name: str
    change: Change
    fields: NotRequired[list[FieldChange]]


class ChangeRecord(TypedDict):
    """One applied-or-planned change, the report artifact's evidence unit."""

    type: str
    name: str
    change: Change
    before: dict[str, str] | None
    after: dict[str, str] | None


def _doc_app(doc: dict[str, Any]) -> str:
    """The app a YAML/JSON doc targets, defaulting like the export writers do."""
    return str(doc.get("app") or "search")


def _write_yaml(path: Path, docs: list[dict[str, Any]]) -> None:
    path.write_text(
        yaml.dump(docs, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    """Load a YAML doc list; a missing file is an empty snapshot, not an error."""
    if not path.exists():
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not loaded:
        return []
    if not isinstance(loaded, list):
        raise ValueError(f"{path}: expected a YAML list of objects")
    return [d for d in loaded if isinstance(d, dict)]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _kv_drift(
    name: str, desired: dict[str, Any], current: dict[str, Any] | None
) -> DriftEntry:
    """Structured drift between a desired key/value map and the live one.

    ``current is None`` means the stanza does not exist live (``added``).
    Shared by parsers and macros — both are conf-stanza key/value objects,
    just under a different conf name.
    """
    if current is None:
        fields: list[FieldChange] = [
            {"field": k, "old": None, "new": str(v)} for k, v in desired.items()
        ]
        entry: DriftEntry = {"name": name, "change": "added"}
        if fields:
            entry["fields"] = fields
        return entry
    changed: list[FieldChange] = [
        {"field": k, "old": str(current.get(k, "")), "new": str(v)}
        for k, v in desired.items()
        if str(current.get(k, "")) != str(v)
    ]
    if changed:
        return {"name": name, "change": "modified", "fields": changed}
    return {"name": name, "change": "unchanged"}


def _hash_drift(name: str, local: bytes | None, remote: bytes | None) -> DriftEntry:
    """Structured drift for a blob (lookup CSV / dashboard XML) by content hash."""
    if remote is None:
        return {
            "name": name,
            "change": "added",
            "fields": [{"field": "sha256", "old": None, "new": _sha256(local or b"")}],
        }
    if local is None:
        return {"name": name, "change": "removed"}
    old_hash, new_hash = _sha256(remote), _sha256(local)
    if old_hash == new_hash:
        return {"name": name, "change": "unchanged"}
    return {
        "name": name,
        "change": "modified",
        "fields": [{"field": "sha256", "old": old_hash, "new": new_hash}],
    }


def change_record(type_name: str, entry: DriftEntry) -> ChangeRecord:
    """Turn one drift entry into a report artifact's before/after evidence unit."""
    fields = entry.get("fields", [])
    before = (
        None
        if entry["change"] == "added"
        else {f["field"]: f["old"] or "" for f in fields} or None
    )
    after = {f["field"]: f["new"] for f in fields} or None
    return {
        "type": type_name,
        "name": entry["name"],
        "change": entry["change"],
        "before": before,
        "after": after,
    }
