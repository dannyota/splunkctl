"""`state` adapter for SOAR assets — field-level JSON config drift.

SOAR assets are JSON config blobs stored per-asset under
``<dir>/soar-assets/<name>.json``.  Password-type config keys are masked
on pull (replaced with ``"****"``) so secrets never land on disk; masked
fields are ignored during diff comparison.  Push uses fetch-merge-post
semantics (same as ``soar assets update``) and never deletes.

Each adapter function builds its own ``SOARClient`` from resolved SOAR
config (``config.resolve_soar()``), so the ``client`` parameter (which
the orchestrator passes as the SIEM client) is accepted for signature
compatibility but ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from splunkctl import config as cfg_mod
from splunkctl.commands.state_types import (
    ChangeRecord,
    DriftEntry,
    _kv_drift,
    change_record,
)
from splunkctl.soar.client import SOARClient, SOARError

_MASKED = "****"
_SUBDIR = "soar-assets"


# ------------------------------------------------------------------
# SOAR client helpers
# ------------------------------------------------------------------


def _build_soar_client() -> SOARClient:
    """Construct a SOARClient from resolved SOAR config (no Click context)."""
    cfg = cfg_mod.resolve_soar()
    host = cfg.get("host")
    if not host:
        raise RuntimeError(
            "No SOAR host configured. Run 'splunkctl config init --soar' "
            "or set SOAR_HOST."
        )
    return SOARClient(
        host=host,
        port=int(cfg.get("port", 8443)),
        token=cfg.get("token"),
        username=cfg.get("username"),
        password=cfg.get("password"),
        verify=bool(cfg.get("verify", False)),
    )


def _list_assets(soar: SOARClient) -> list[dict[str, Any]]:
    """GET all assets from the SOAR REST API."""
    result = soar.get("asset", params={"page_size": 0})
    data: list[dict[str, Any]] = (
        result.get("data", []) if isinstance(result, dict) else []
    )
    return [a for a in data if isinstance(a, dict)]


def _get_asset(soar: SOARClient, asset_id: int) -> dict[str, Any]:
    """GET a single asset by ID."""
    result = soar.get(f"asset/{asset_id}", params={})
    if not isinstance(result, dict):
        raise SOARError(f"Asset {asset_id} not found", kind="not_found")
    return result


# ------------------------------------------------------------------
# secret masking
# ------------------------------------------------------------------


def _password_keys(soar: SOARClient, app_id: int | None) -> set[str]:
    """Return config keys with ``data_type: password`` from the app schema."""
    if app_id is None:
        return set()
    try:
        app = soar.get(f"app/{app_id}", params={})
    except SOARError:
        return set()
    if not isinstance(app, dict):
        return set()
    schema = app.get("configuration", {})
    if not isinstance(schema, dict):
        return set()
    return {
        k
        for k, v in schema.items()
        if isinstance(v, dict) and v.get("data_type") == "password"
    }


def _mask_config(config: dict[str, Any], secret_keys: set[str]) -> dict[str, Any]:
    """Return a copy of *config* with password-type values replaced."""
    return {k: _MASKED if k in secret_keys else v for k, v in config.items()}


# ------------------------------------------------------------------
# serialization helpers
# ------------------------------------------------------------------


def _asset_to_doc(asset: dict[str, Any], secret_keys: set[str]) -> dict[str, Any]:
    """Serialize a SOAR asset API response to an on-disk document.

    Masks password-type config values so secrets never land on disk.
    Preserves only the fields needed for diff/push round-tripping.
    """
    config = asset.get("configuration", {}) or {}
    doc: dict[str, Any] = {
        "id": asset.get("id"),
        "name": asset.get("name", ""),
        "app_id": asset.get("app"),
        "description": asset.get("description", ""),
        "configuration": (
            _mask_config(config, secret_keys) if secret_keys else dict(config)
        ),
        "tags": asset.get("tags", []),
    }
    return doc


def _safe_filename(name: str) -> str:
    """Sanitize an asset name for use as a filename."""
    return name.replace("/", "_").replace("\\", "_").replace("\x00", "_")


def _read_local_assets(dir_path: Path) -> dict[str, dict[str, Any]]:
    """Load all ``<dir>/soar-assets/<name>.json`` files, keyed by name."""
    sub = dir_path / _SUBDIR
    if not sub.is_dir():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for p in sorted(sub.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(doc, dict) and doc.get("name"):
            result[str(doc["name"])] = doc
    return result


def _flat_config(doc: dict[str, Any], secret_keys: set[str]) -> dict[str, str]:
    """Flatten config + metadata into a comparable key-value map.

    Excludes masked (``****``) keys so secrets redacted on pull never
    cause false-positive drift.
    """
    kv: dict[str, str] = {}
    kv["description"] = str(doc.get("description", ""))
    kv["app_id"] = str(doc.get("app_id", ""))
    config = doc.get("configuration", {}) or {}
    for k, v in sorted(config.items()):
        if k in secret_keys or v == _MASKED:
            continue
        kv[f"config.{k}"] = str(v)
    return kv


# ------------------------------------------------------------------
# pull
# ------------------------------------------------------------------


def pull_soar_assets(client: Any, dir_path: Path, app: str | None) -> int:
    """Snapshot all SOAR assets to ``<dir>/soar-assets/<name>.json``.

    The *app* and *client* parameters are accepted for signature
    compatibility but ignored -- SOAR assets are not scoped by Splunk
    app, and the SOAR client is built internally.
    """
    soar = _build_soar_client()
    assets = _list_assets(soar)

    out_dir = dir_path / _SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for asset in assets:
        name = asset.get("name", "")
        if not name:
            continue
        app_id = asset.get("app")
        secret_keys = _password_keys(soar, int(app_id) if app_id is not None else None)
        doc = _asset_to_doc(asset, secret_keys)
        fname = _safe_filename(name) + ".json"
        (out_dir / fname).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


# ------------------------------------------------------------------
# diff
# ------------------------------------------------------------------


def diff_soar_assets(client: Any, dir_path: Path, app: str | None) -> list[DriftEntry]:
    """Compare local JSON files against live SOAR assets."""
    soar = _build_soar_client()
    assets = _list_assets(soar)
    local = _read_local_assets(dir_path)

    # Cache password keys per app to avoid repeated lookups.
    app_secrets: dict[int, set[str]] = {}
    for asset in assets:
        aid = asset.get("app")
        if aid is not None and int(aid) not in app_secrets:
            app_secrets[int(aid)] = _password_keys(soar, int(aid))

    entries: list[DriftEntry] = []
    seen: set[str] = set()

    for asset in assets:
        name = str(asset.get("name", ""))
        if not name:
            continue
        seen.add(name)
        aid = asset.get("app")
        secret_keys = app_secrets.get(int(aid), set()) if aid is not None else set()
        remote_doc = _asset_to_doc(asset, secret_keys)
        remote_kv = _flat_config(remote_doc, secret_keys)

        local_doc = local.get(name)
        if local_doc is None:
            entries.append({"name": name, "change": "removed"})
            continue

        local_kv = _flat_config(local_doc, secret_keys)
        entries.append(_kv_drift(name, local_kv, remote_kv))

    # Local-only assets -> added.
    for name in local:
        if name not in seen:
            local_doc = local[name]
            local_kv = _flat_config(local_doc, set())
            entries.append(_kv_drift(name, local_kv, None))

    return entries


# ------------------------------------------------------------------
# apply (push)
# ------------------------------------------------------------------


def apply_soar_assets(
    client: Any, dir_path: Path, app: str | None
) -> list[ChangeRecord]:
    """Create missing assets and update modified ones (fetch-merge-post).

    Never deletes.  Secrets in local files are applied as-is (the
    operator fills them in before push).  Masked (``****``) values are
    stripped on create and skipped during merge on update.
    """
    soar = _build_soar_client()
    assets = _list_assets(soar)
    remote_by_name: dict[str, dict[str, Any]] = {}
    for a in assets:
        n = a.get("name", "")
        if n:
            remote_by_name[n] = a

    local = _read_local_assets(dir_path)
    app_secrets: dict[int, set[str]] = {}
    records: list[ChangeRecord] = []

    for name, local_doc in local.items():
        remote = remote_by_name.get(name)

        if remote is None:
            # Create -- added asset.
            body: dict[str, Any] = {"name": name}
            if local_doc.get("app_id") is not None:
                body["app_id"] = local_doc["app_id"]
            if local_doc.get("description"):
                body["description"] = local_doc["description"]
            config = local_doc.get("configuration", {}) or {}
            # Strip masked values -- cannot create with placeholders.
            clean = {k: v for k, v in config.items() if v != _MASKED}
            if clean:
                body["configuration"] = clean

            soar.post("asset", body=body)

            local_kv = _flat_config(local_doc, set())
            entry = _kv_drift(name, local_kv, None)
            records.append(change_record("soar-assets", entry))
        else:
            # Check if update needed.
            aid = remote.get("app")
            if aid is not None and int(aid) not in app_secrets:
                app_secrets[int(aid)] = _password_keys(soar, int(aid))
            secret_keys = app_secrets.get(int(aid), set()) if aid is not None else set()

            remote_doc = _asset_to_doc(remote, secret_keys)
            remote_kv = _flat_config(remote_doc, secret_keys)
            local_kv = _flat_config(local_doc, secret_keys)
            entry = _kv_drift(name, local_kv, remote_kv)
            if entry["change"] != "modified":
                continue

            # Fetch-merge-post (same as ``soar assets update``).
            asset_id = remote["id"]
            existing = _get_asset(soar, int(asset_id))
            old_config: dict[str, Any] = existing.get("configuration", {}) or {}
            new_config = local_doc.get("configuration", {}) or {}
            # Merge: local wins, but skip masked values.
            merged = dict(old_config)
            for k, v in new_config.items():
                if v != _MASKED:
                    merged[k] = v

            body = {
                "name": local_doc.get("name", name),
                "configuration": merged,
            }
            if local_doc.get("description") is not None:
                body["description"] = local_doc["description"]
            # Preserve app association.
            app_ref = existing.get("app")
            if app_ref is not None:
                body["app_id"] = app_ref

            soar.post(f"asset/{asset_id}", body=body)
            records.append(change_record("soar-assets", entry))

    return records
