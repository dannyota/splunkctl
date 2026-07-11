"""CIM-to-CEF field mapping and row-to-artifact transform.

Pure functions and data — no I/O. The ``CIM_CEF_MAP`` encodes the official
Splunk SOAR Connector for Splunk mapping (``bytesIn`` typo fixed).
``CEF_CONTAINS_MAP`` maps CEF keys to SOAR contains types for artifact
actionability. ``SEVERITY_MAP`` converts Splunk severity/urgency strings
to SOAR severity levels.

Used by ``soar ingest`` (CLI) and ``soar artifacts create`` (auto cef_types).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# ---- CIM -> CEF default map ------------------------------------------------
# Source: github.com/splunk-soar-connectors/splunk src/splunk_consts.py
# Fixed: upstream has ``butesIn`` typo for bytes_in -> ships as ``bytesIn``.

CIM_CEF_MAP: dict[str, str] = {
    "action": "act",
    "action_name": "act",
    "app": "app",
    "bytes_in": "bytesIn",
    "bytes_out": "bytesOut",
    "category": "cat",
    "dest": "destinationAddress",
    "dest_ip": "destinationAddress",
    "dest_mac": "destinationMacAddress",
    "dest_nt_domain": "destinationNtDomain",
    "dest_port": "destinationPort",
    "dest_translated_ip": "destinationTranslatedAddress",
    "dest_translated_port": "destinationTranslatedPort",
    "direction": "deviceDirection",
    "dns": "destinationDnsDomain",
    "dvc": "dvc",
    "dvc_ip": "deviceAddress",
    "dvc_mac": "deviceMacAddress",
    "file_create_time": "fileCreateTime",
    "file_hash": "fileHash",
    "file_modify_time": "fileModificationTime",
    "file_name": "fileName",
    "file_path": "filePath",
    "file_size": "fileSize",
    "message": "message",
    "protocol": "transportProtocol",
    "transport": "transportProtocol",
    "request_payload": "request",
    "request_payload_type": "requestMethod",
    "src": "sourceAddress",
    "src_dns": "sourceDnsDomain",
    "src_ip": "sourceAddress",
    "src_mac": "sourceMacAddress",
    "src_nt_domain": "sourceNtDomain",
    "src_port": "sourcePort",
    "src_translated_ip": "sourceTranslatedAddress",
    "src_translated_port": "sourceTranslatedPort",
    "src_user": "sourceUserId",
    "url": "requestURL",
    "user": "destinationUserName",
    "user_id": "destinationUserId",
}

# ---- CEF contains-type map (canonical) -------------------------------------
# Maps CEF key -> list of SOAR contains types.  Imported by
# ``splunkctl/commands/soar/artifacts.py`` for auto cef_types on create.

CEF_CONTAINS_MAP: dict[str, list[str]] = {
    "destinationAddress": ["ip", "host name"],
    "destinationMacAddress": ["mac address"],
    "destinationNtDomain": ["domain"],
    "destinationPort": ["port"],
    "destinationTranslatedAddress": ["ip"],
    "destinationTranslatedPort": ["port"],
    "destinationDnsDomain": ["domain"],
    "dvc": ["ip", "host name"],
    "deviceAddress": ["ip"],
    "deviceMacAddress": ["mac address"],
    "fileHash": ["hash"],
    "fileName": ["file name"],
    "filePath": ["file path"],
    "sourceAddress": ["ip", "host name"],
    "sourceDnsDomain": ["domain"],
    "sourceMacAddress": ["mac address"],
    "sourceNtDomain": ["domain"],
    "sourcePort": ["port"],
    "sourceTranslatedAddress": ["ip"],
    "sourceTranslatedPort": ["port"],
    "sourceUserId": ["user name"],
    "requestURL": ["url"],
    "destinationUserName": ["user name"],
    "destinationUserId": ["user name"],
}

# ---- Severity map -----------------------------------------------------------
# Check ``severity`` first, then ``urgency``; default ``medium``.
# Multivalue -> highest wins.

_SEVERITY_ORDER: dict[str, int] = {
    "informational": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_SPLUNK_TO_SOAR: dict[str, str] = {
    "informational": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "high",
}


def map_severity(row: dict[str, Any]) -> str:
    """Derive SOAR severity from a Splunk result row.

    Checks ``severity`` first, then ``urgency``. If both are absent,
    returns ``medium``. When the field contains multiple values
    (comma-separated or list), the highest wins.
    """
    raw = row.get("severity") or row.get("urgency") or ""
    if isinstance(raw, list):
        values = [str(v).strip().lower() for v in raw if v]
    else:
        values = [v.strip().lower() for v in str(raw).split(",") if v.strip()]

    if not values:
        return "medium"

    best_rank = -1
    best_sev = "medium"
    for v in values:
        rank = _SEVERITY_ORDER.get(v, -1)
        if rank > best_rank:
            best_rank = rank
            best_sev = _SPLUNK_TO_SOAR.get(v, "medium")
    return best_sev


# ---- Row -> artifact transform ----------------------------------------------


def row_sdi(row: dict[str, Any], sdi_field: str) -> str:
    """Compute the source_data_identifier for a result row.

    If ``sdi_field`` names a field present in the row, use its value.
    Otherwise hash the full row (SHA-256).
    """
    val = row.get(sdi_field)
    if val is not None and str(val).strip():
        return str(val).strip()
    canonical = json.dumps(row, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def row_to_cef(
    row: dict[str, Any],
    *,
    cim_map: dict[str, str] | None = None,
    include_unmapped: bool = False,
) -> dict[str, str]:
    """Map a Splunk result row to a CEF dict.

    Args:
        row: Single Splunk result dict.
        cim_map: CIM->CEF mapping; defaults to ``CIM_CEF_MAP``.
        include_unmapped: If True, fields not in the map are passed
            through as custom CEF keys.

    Returns:
        CEF dict suitable for ``POST /rest/artifact``.
    """
    effective = cim_map if cim_map is not None else CIM_CEF_MAP
    cef: dict[str, str] = {}
    mapped_keys: set[str] = set()

    for cim_field, cef_key in effective.items():
        val = row.get(cim_field)
        if val is not None and str(val).strip():
            cef[cef_key] = str(val)
            mapped_keys.add(cim_field)

    if include_unmapped:
        skip = {"_raw", "_time", "_si", "_serial", "_sourcetype", "_indextime"}
        for key, val in row.items():
            if key in mapped_keys or key in skip or key.startswith("_"):
                continue
            if key in effective:
                continue
            if val is not None and str(val).strip():
                cef[key] = str(val)

    return cef


def auto_cef_types(
    cef: dict[str, Any],
    *,
    contains_map: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Build cef_types from the contains map for a CEF dict."""
    effective = contains_map if contains_map is not None else CEF_CONTAINS_MAP
    types: dict[str, list[str]] = {}
    for key in cef:
        if key in effective:
            types[key] = effective[key]
    return types


def container_name_for_row(
    row: dict[str, Any],
    *,
    template: str | None = None,
    name_field: str | None = None,
) -> str:
    """Derive a container name for a result row.

    Priority:
    1. ``name_field`` — use that row field's value.
    2. ``template`` — use as literal name.
    3. ``rule_name`` field (ES notable convention).
    4. Fallback ``"Splunk Log Entry on <_time>: <source>"``.
    """
    if name_field:
        val = row.get(name_field)
        if val and str(val).strip():
            return str(val).strip()

    if template:
        return template

    rule_name = row.get("rule_name") or row.get("search_name")
    if rule_name and str(rule_name).strip():
        return str(rule_name).strip()

    _time = row.get("_time", "unknown")
    source = row.get("source", "unknown")
    return f"Splunk Log Entry on {_time}: {source}"


def artifact_name_for_row(row: dict[str, Any]) -> str:
    """Derive an artifact name for a result row.

    Uses ``search_name`` if present, else ``"Field Values"``
    (connector convention).
    """
    name = row.get("search_name")
    if name and str(name).strip():
        return str(name).strip()
    return "Field Values"
