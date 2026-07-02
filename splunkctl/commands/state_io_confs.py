"""`state` adapters for parsers (props/transforms) and macros.

Both are conf-stanza key/value objects, just under different conf
names — parsers under ``props``/``transforms``, macros under
``macros``. Reuses ``parsers_io``'s explicit-key reader
(``_explicit_keys``, conf-name-agnostic) for pull/diff on both, and
their existing apply paths: ``parsers_io._apply_stanza`` for parsers,
``conf_ops.set_keys`` for macros — the same core ``conf``/``macros
set``/``lookups define`` already share. No apply/serialization logic
is re-implemented here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from splunkctl.commands import conf_ops
from splunkctl.commands.parsers_io import _CONFS, _apply_stanza, _explicit_keys
from splunkctl.commands.state_types import (
    ChangeRecord,
    DriftEntry,
    _doc_app,
    _kv_drift,
    _load_yaml_list,
    _write_yaml,
    change_record,
)


def _stanza_app(stanza: Any) -> str:
    acl: dict[str, Any] = dict(stanza.access)
    return str(acl.get("app", "search") or "search")


def _conf_app_scope(app: str | None) -> dict[str, str]:
    return {} if app is None else {"app": app, "owner": "-"}


# --------------------------------------------------------------------------
# parsers (props/transforms)
# --------------------------------------------------------------------------


def pull_parsers(client: Any, dir_path: Path, app: str | None) -> int:
    """Snapshot props/transforms stanzas with explicit keys.

    Reuses ``_explicit_keys``, the same reader ``parsers export`` uses.
    """
    svc = client.service
    docs: list[dict[str, Any]] = []
    for cf in _CONFS:
        for stanza in svc.confs[cf].list():
            stanza_app = _stanza_app(stanza)
            if app is not None and stanza_app != app:
                continue
            keys = _explicit_keys(svc, cf, stanza.name, stanza_app)
            if not keys:
                continue
            acl: dict[str, Any] = dict(stanza.access)
            docs.append(
                {
                    "conf": cf,
                    "stanza": stanza.name,
                    "app": stanza_app,
                    "sharing": acl.get("sharing", ""),
                    "keys": keys,
                }
            )
    _write_yaml(dir_path / "parsers.yml", docs)
    return len(docs)


def diff_parsers(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Classify every on-disk stanza plus any live stanza missing from disk."""
    svc = client.service
    docs = _load_yaml_list(dir_path / "parsers.yml")
    disk_names: set[str] = set()
    entries: list[DriftEntry] = []
    for doc in docs:
        if not doc.get("stanza"):
            continue
        conf_name = str(doc.get("conf", "props"))
        stanza_name = str(doc["stanza"])
        doc_app = _doc_app(doc)
        if app is not None and doc_app != app:
            continue
        name = f"{conf_name}:{stanza_name}"
        disk_names.add(name)
        current = _explicit_keys(svc, conf_name, stanza_name, doc_app)
        entries.append(_kv_drift(name, doc.get("keys") or {}, current))
    for cf in _CONFS:
        for stanza in svc.confs[cf].list():
            stanza_app = _stanza_app(stanza)
            if app is not None and stanza_app != app:
                continue
            keys = _explicit_keys(svc, cf, stanza.name, stanza_app)
            if not keys:
                continue
            name = f"{cf}:{stanza.name}"
            if name in disk_names:
                continue
            entries.append({"name": name, "change": "removed"})
    return entries


def apply_parsers(client: Any, dir_path: Path, app: str | None) -> list[ChangeRecord]:
    """Apply added/modified on-disk stanzas via ``parsers_io._apply_stanza``."""
    svc = client.service
    docs = _load_yaml_list(dir_path / "parsers.yml")
    records: list[ChangeRecord] = []
    for doc in docs:
        if not doc.get("stanza"):
            continue
        conf_name = str(doc.get("conf", "props"))
        stanza_name = str(doc["stanza"])
        doc_app = _doc_app(doc)
        if app is not None and doc_app != app:
            continue
        desired = doc.get("keys") or {}
        if not desired:
            continue
        current = _explicit_keys(svc, conf_name, stanza_name, doc_app)
        entry = _kv_drift(f"{conf_name}:{stanza_name}", desired, current)
        if entry["change"] not in ("added", "modified"):
            continue
        _apply_stanza(client, doc)
        records.append(change_record("parsers", entry))
    return records


# --------------------------------------------------------------------------
# macros
# --------------------------------------------------------------------------


def pull_macros(client: Any, dir_path: Path, app: str | None) -> int:
    """Snapshot macros.conf stanzas with explicit keys (reuses ``_explicit_keys``)."""
    svc = client.service
    docs: list[dict[str, Any]] = []
    for stanza in svc.confs["macros"].list(**_conf_app_scope(app)):
        stanza_app = _stanza_app(stanza)
        keys = _explicit_keys(svc, "macros", stanza.name, stanza_app)
        if not keys:
            continue
        docs.append({"name": stanza.name, "app": stanza_app, "keys": keys})
    _write_yaml(dir_path / "macros.yml", docs)
    return len(docs)


def diff_macros(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Classify every on-disk macro plus any live macro missing from disk."""
    svc = client.service
    docs = _load_yaml_list(dir_path / "macros.yml")
    disk_names: set[str] = set()
    entries: list[DriftEntry] = []
    for doc in docs:
        if not doc.get("name"):
            continue
        name = str(doc["name"])
        doc_app = _doc_app(doc)
        if app is not None and doc_app != app:
            continue
        disk_names.add(name)
        current = _explicit_keys(svc, "macros", name, doc_app)
        entries.append(_kv_drift(name, doc.get("keys") or {}, current))
    for stanza in svc.confs["macros"].list(**_conf_app_scope(app)):
        stanza_app = _stanza_app(stanza)
        if app is not None and stanza_app != app:
            continue
        keys = _explicit_keys(svc, "macros", stanza.name, stanza_app)
        if not keys or stanza.name in disk_names:
            continue
        entries.append({"name": stanza.name, "change": "removed"})
    return entries


def apply_macros(client: Any, dir_path: Path, app: str | None) -> list[ChangeRecord]:
    """Apply added/modified on-disk macros via ``conf_ops.set_keys``."""
    svc = client.service
    docs = _load_yaml_list(dir_path / "macros.yml")
    records: list[ChangeRecord] = []
    for doc in docs:
        if not doc.get("name"):
            continue
        name = str(doc["name"])
        doc_app = _doc_app(doc)
        if app is not None and doc_app != app:
            continue
        desired = doc.get("keys") or {}
        if not desired:
            continue
        current = _explicit_keys(svc, "macros", name, doc_app)
        entry = _kv_drift(name, desired, current)
        if entry["change"] not in ("added", "modified"):
            continue
        kv = {k: str(v) for k, v in desired.items()}
        conf_ops.set_keys(client, "macros", name, kv, app=app)
        records.append(change_record("macros", entry))
    return records
