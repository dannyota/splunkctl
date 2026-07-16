"""`state` adapter for SOAR playbooks — tgz-export hash-drift blobs.

Playbooks are opaque tgz archives exported/imported via the SOAR
REST API (``/rest/playbook/<id>/export``, ``/rest/import_playbook``).
Drift is a whole-archive content hash (``_hash_drift``), not a
per-field diff -- the tgz contains JSON + Python and is not
meaningfully diffable at field level.

Pull exports each playbook to ``<dir>/soar-playbooks/<name>.tgz``.
Diff compares local tgz hashes against live exports.
Push imports added/modified playbooks via ``import_playbook``.
Push never deletes -- a live playbook absent from disk is classified
``removed`` and reported, never touched.

The adapter functions receive a ``SOARClient`` (not a ``SplunkClient``)
-- the ``SOAR_TYPES`` set in ``state_io.py`` tells the orchestrator
which client to pass.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from splunkctl.commands.state_types import (
    ChangeRecord,
    DriftEntry,
    _hash_drift,
    change_record,
)


def _list_playbooks(client: Any) -> list[dict[str, Any]]:
    """List all playbooks, paginating through all pages."""
    items: list[dict[str, Any]] = list(client.iter_pages("playbook"))
    return items


def _export_tgz(client: Any, playbook_id: int) -> bytes:
    """Export a playbook as a tgz archive (raw bytes)."""
    result: bytes = client.get_bytes(f"playbook/{playbook_id}/export", params={})
    return result


def _safe_filename(name: str) -> str:
    """Sanitize a playbook name for use as a filename.

    SOAR playbook names are scoped ``<dir>/<module>``; replace the
    slash with ``__`` so the file is a flat sibling, not a subdirectory.
    """
    return name.replace("/", "__")


def _name_from_filename(filename: str) -> str:
    """Reverse ``_safe_filename``: ``dir__module`` -> ``dir/module``."""
    stem = filename.removesuffix(".tgz")
    return stem.replace("__", "/", 1)


def pull_soar_playbooks(client: Any, dir_path: Path, app: str | None) -> int:
    """Export every SOAR playbook to ``<dir>/soar-playbooks/<name>.tgz``.

    The *app* parameter is accepted for signature compatibility but
    ignored — SOAR playbooks are not scoped by Splunk app.
    """
    out_dir = dir_path / "soar-playbooks"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write an index mapping filename -> {id, name} for diff/push
    # to resolve names back to ids without extra API calls.
    playbooks = _list_playbooks(client)
    index: list[dict[str, Any]] = []
    count = 0
    for pb in playbooks:
        pb_id = int(pb["id"])
        name = str(pb.get("name", f"playbook_{pb_id}"))
        tgz = _export_tgz(client, pb_id)
        fname = _safe_filename(name) + ".tgz"
        (out_dir / fname).write_bytes(tgz)
        index.append({"id": pb_id, "name": name, "filename": fname})
        count += 1

    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return count


def _load_index(dir_path: Path) -> list[dict[str, Any]]:
    """Load the soar-playbooks index.json, or empty list if missing."""
    idx_path = dir_path / "soar-playbooks" / "index.json"
    if not idx_path.exists():
        return []
    return json.loads(idx_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def diff_soar_playbooks(
    client: Any, dir_path: Path, app: str | None
) -> list[DriftEntry]:
    """Hash-compare every live playbook's tgz against its on-disk file."""
    local_dir = dir_path / "soar-playbooks"
    index = _load_index(dir_path)
    local_by_name: dict[str, Path] = {}
    for entry in index:
        fpath = local_dir / entry["filename"]
        if fpath.exists():
            local_by_name[entry["name"]] = fpath

    # Also pick up any tgz files not in the index (manually added)
    if local_dir.is_dir():
        for p in local_dir.glob("*.tgz"):
            inferred_name = _name_from_filename(p.name)
            if inferred_name not in local_by_name:
                local_by_name[inferred_name] = p

    entries: list[DriftEntry] = []
    seen: set[str] = set()

    for pb in _list_playbooks(client):
        name = str(pb.get("name", f"playbook_{pb['id']}"))
        seen.add(name)
        remote_tgz = _export_tgz(client, int(pb["id"]))
        local_path = local_by_name.get(name)
        local_bytes = local_path.read_bytes() if local_path is not None else None
        entries.append(_hash_drift(name, local_bytes, remote_tgz))

    # Local-only playbooks (added)
    for name, path in local_by_name.items():
        if name not in seen:
            entries.append(_hash_drift(name, path.read_bytes(), None))

    return entries


def apply_soar_playbooks(
    client: Any, dir_path: Path, app: str | None
) -> list[ChangeRecord]:
    """Import added/modified on-disk playbook tgz files.

    Re-diffs each playbook, then imports those classified as added or
    modified via ``POST /rest/import_playbook`` with the tgz base64-encoded.
    Never deletes — a live playbook absent from disk is skipped.
    """
    local_dir = dir_path / "soar-playbooks"
    if not local_dir.is_dir():
        return []

    index = _load_index(dir_path)
    local_by_name: dict[str, Path] = {}
    for idx_entry in index:
        fpath = local_dir / idx_entry["filename"]
        if fpath.exists():
            local_by_name[idx_entry["name"]] = fpath
    for p in local_dir.glob("*.tgz"):
        inferred_name = _name_from_filename(p.name)
        if inferred_name not in local_by_name:
            local_by_name[inferred_name] = p

    # Build a remote name -> id + tgz map for diff
    remote_map: dict[str, tuple[int, bytes]] = {}
    for pb in _list_playbooks(client):
        name = str(pb.get("name", f"playbook_{pb['id']}"))
        remote_map[name] = (int(pb["id"]), _export_tgz(client, int(pb["id"])))

    records: list[ChangeRecord] = []
    for name, path in sorted(local_by_name.items(), key=lambda x: x[0]):
        local_bytes = path.read_bytes()
        remote_info = remote_map.get(name)
        if remote_info is None:
            drift = _hash_drift(name, local_bytes, None)
        else:
            drift = _hash_drift(name, local_bytes, remote_info[1])

        if drift["change"] not in ("added", "modified"):
            continue

        encoded = base64.b64encode(local_bytes).decode()
        body: dict[str, Any] = {
            "playbook": encoded,
            "scm": "local",
            "force": True,
        }
        client.post("import_playbook", body=body)
        records.append(change_record("soar-playbooks", drift))

    return records


# ------------------------------------------------------------------
# soar-lists (decided_list)
# ------------------------------------------------------------------

_LIST_EP = "decided_list"


def _serialize_list_content(content: list[list[str]]) -> bytes:
    """Canonical JSON bytes for a list's content (matches ``soar lists export``)."""
    return (json.dumps(content, indent=2) + "\n").encode("utf-8")


def _list_all_lists(client: Any) -> list[dict[str, Any]]:
    """Fetch every custom list (paginated)."""
    return list(client.iter_pages(_LIST_EP))


def pull_soar_lists(client: Any, dir_path: Path, app: str | None) -> int:
    """Download every custom list to ``<dir>/soar-lists/<name>.json``.

    The *app* parameter is accepted for signature compatibility but
    ignored — SOAR lists are not scoped by Splunk app.
    """
    out_dir = dir_path / "soar-lists"
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in _list_all_lists(client):
        list_id = item.get("id")
        name: str = item.get("name", str(list_id))
        detail = client.get(f"{_LIST_EP}/{list_id}", params={})
        content: list[list[str]] = (
            detail.get("content", []) if isinstance(detail, dict) else []
        )
        (out_dir / f"{name}.json").write_bytes(_serialize_list_content(content))
        count += 1
    return count


def diff_soar_lists(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Hash-compare every live custom list against its on-disk JSON."""
    local_dir = dir_path / "soar-lists"
    local_files = (
        {p.stem: p for p in local_dir.glob("*.json")} if local_dir.is_dir() else {}
    )

    entries: list[DriftEntry] = []
    seen: set[str] = set()

    for item in _list_all_lists(client):
        list_id = item.get("id")
        name = str(item.get("name", list_id))
        seen.add(name)

        detail = client.get(f"{_LIST_EP}/{list_id}", params={})
        content: list[list[str]] = (
            detail.get("content", []) if isinstance(detail, dict) else []
        )
        remote_bytes = _serialize_list_content(content)

        local_path = local_files.get(name)
        local_bytes = local_path.read_bytes() if local_path is not None else None
        entries.append(_hash_drift(name, local_bytes, remote_bytes))

    # Local-only files -> added.
    for name, path in local_files.items():
        if name not in seen:
            entries.append(_hash_drift(name, path.read_bytes(), None))

    return entries


def apply_soar_lists(
    client: Any, dir_path: Path, app: str | None
) -> list[ChangeRecord]:
    """Create or full-replace added/modified lists.  Never deletes."""
    local_dir = dir_path / "soar-lists"
    if not local_dir.is_dir():
        return []

    # Build name -> remote metadata map.
    remote: dict[str, dict[str, Any]] = {}
    for item in _list_all_lists(client):
        name = str(item.get("name", item.get("id")))
        remote[name] = item

    records: list[ChangeRecord] = []
    for path in sorted(local_dir.glob("*.json")):
        name = path.stem
        local_bytes = path.read_bytes()
        local_content: list[list[str]] = json.loads(local_bytes)

        existing = remote.get(name)
        if existing is None:
            # Added: create.
            entry = _hash_drift(name, local_bytes, None)
            if entry["change"] != "added":
                continue
            client.post(_LIST_EP, body={"name": name, "content": local_content})
        else:
            # Fetch live content and compare hashes.
            list_id = existing["id"]
            detail = client.get(f"{_LIST_EP}/{list_id}", params={})
            remote_content: list[list[str]] = (
                detail.get("content", []) if isinstance(detail, dict) else []
            )
            remote_bytes = _serialize_list_content(remote_content)
            entry = _hash_drift(name, local_bytes, remote_bytes)
            if entry["change"] != "modified":
                continue
            client.post(f"{_LIST_EP}/{list_id}", body={"content": local_content})

        records.append(change_record("soar-lists", entry))
    return records
