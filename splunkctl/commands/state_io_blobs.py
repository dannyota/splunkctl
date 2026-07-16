"""`state` adapters for lookups and dashboards -- content-hash blobs.

Unlike rules/parsers/macros (field-oriented conf objects), a lookup CSV
and a dashboard's XML are opaque blobs: drift is a whole-file content
hash comparison (``state_types._hash_drift``), not a per-field diff.
Lookups apply via ``client.upload_lookup`` (the same Web-UI-backed path
`lookups upload`/`update` use) after a fresh oneshot ``| inputlookup``
read, exactly like `lookups download`. Dashboards are pull+diff ONLY —
no import path exists in the SDK fork or the CLI, so there is no
``apply_dashboards`` here; ``state_io.APPLY_FNS`` has no "dashboards"
entry and callers must not attempt to write them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from splunkctl.commands.common import spl_quote_lookup_name
from splunkctl.commands.state_types import (
    ChangeRecord,
    DriftEntry,
    _hash_drift,
    change_record,
)

# --------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------


def _download_csv(svc: Any, name: str, app: str) -> bytes:
    quoted = spl_quote_lookup_name(name)
    stream = svc.jobs.oneshot(f"| inputlookup {quoted}", output_mode="csv", app=app)
    result: bytes = stream.read()
    return result


def pull_lookups(client: Any, dir_path: Path, app: str | None) -> int:
    """Download every lookup table's CSV to ``<dir>/lookups/<name>``."""
    svc = client.service
    out_dir = dir_path / "lookups"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for lk in svc.lookup_table_files.list(app=app or "-", owner="-"):
        content = _download_csv(svc, lk.name, lk.access.app)
        (out_dir / lk.name).write_bytes(content)
        count += 1
    return count


def diff_lookups(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Hash-compare every live lookup's CSV against its on-disk file."""
    svc = client.service
    local_dir = dir_path / "lookups"
    local_files = {p.name: p for p in local_dir.glob("*")} if local_dir.is_dir() else {}
    entries: list[DriftEntry] = []
    seen: set[str] = set()
    for lk in svc.lookup_table_files.list(app=app or "-", owner="-"):
        seen.add(lk.name)
        remote = _download_csv(svc, lk.name, lk.access.app)
        local_path = local_files.get(lk.name)
        local = local_path.read_bytes() if local_path is not None else None
        entries.append(_hash_drift(lk.name, local, remote))
    for name, path in local_files.items():
        if name not in seen:
            entries.append(_hash_drift(name, path.read_bytes(), None))
    return entries


def apply_lookups(client: Any, dir_path: Path, app: str | None) -> list[ChangeRecord]:
    """Upload added/modified on-disk CSVs via ``client.upload_lookup``."""
    svc = client.service
    local_dir = dir_path / "lookups"
    if not local_dir.is_dir():
        return []
    remote = {
        lk.name: lk for lk in svc.lookup_table_files.list(app=app or "-", owner="-")
    }
    records: list[ChangeRecord] = []
    for path in sorted(local_dir.glob("*")):
        name = path.name
        local = path.read_bytes()
        lk = remote.get(name)
        if lk is None:
            entry = _hash_drift(name, local, None)
            if entry["change"] != "added":
                continue
            client.upload_lookup(name, path, app=app or "search", update=False)
        else:
            remote_bytes = _download_csv(svc, name, lk.access.app)
            entry = _hash_drift(name, local, remote_bytes)
            if entry["change"] != "modified":
                continue
            client.upload_lookup(name, path, app=lk.access.app, update=True)
        records.append(change_record("lookups", entry))
    return records


# --------------------------------------------------------------------------
# dashboards -- pull + diff ONLY, no apply path exists
# --------------------------------------------------------------------------


def _is_dashboard(d: Any) -> bool:
    return str(d.content.get("isDashboard", False)) not in ("0", "False")


def pull_dashboards(client: Any, dir_path: Path, app: str | None) -> int:
    """Export every dashboard's XML to ``<dir>/dashboards/<name>.xml``."""
    svc = client.service
    out_dir = dir_path / "dashboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for d in svc.dashboards.list(app=app or "-", owner="-"):
        if not _is_dashboard(d):
            continue
        (out_dir / f"{d.name}.xml").write_text(d.export(), encoding="utf-8")
        count += 1
    return count


def diff_dashboards(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Hash-compare every live dashboard's XML against its on-disk file."""
    svc = client.service
    local_dir = dir_path / "dashboards"
    local_files = (
        {p.stem: p for p in local_dir.glob("*.xml")} if local_dir.is_dir() else {}
    )
    entries: list[DriftEntry] = []
    seen: set[str] = set()
    for d in svc.dashboards.list(app=app or "-", owner="-"):
        if not _is_dashboard(d):
            continue
        seen.add(d.name)
        local_path = local_files.get(d.name)
        local = local_path.read_bytes() if local_path is not None else None
        entries.append(_hash_drift(d.name, local, d.export().encode("utf-8")))
    for name, path in local_files.items():
        if name not in seen:
            entries.append(_hash_drift(name, path.read_bytes(), None))
    return entries
