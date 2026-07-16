"""ES threat-intelligence management — list, upload, delete TI items.

Feature-detected: every subcommand checks for the ``SplunkEnterpriseSecuritySuite``
app before acting, via :func:`splunkctl.commands.es._require_es`.

The REST surface (``/services/data/threat_intel/item`` and
``/services/data/threat_intel/upload``) is ES-only and not covered by the
Python SDK, so all calls go through ``service.get/post/delete`` directly
with ``output_mode=json``.
"""

import json
from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.es import _require_es

_TI_ITEM_PATH = "/services/data/threat_intel/item"
_TI_UPLOAD_PATH = "/services/data/threat_intel/upload"

_INTEL_TYPES = (
    "ip_intel",
    "domain_intel",
    "file_intel",
    "email_intel",
    "http_intel",
    "certificate_intel",
    "registry_intel",
    "service_intel",
    "user_intel",
    "process_intel",
)


def _parse_entries(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Splunk REST JSON envelope into display rows."""
    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        content: dict[str, Any] = entry.get("content", {})
        row: dict[str, Any] = {
            "key": entry.get("name", ""),
            "threat_collection": content.get("threat_collection", ""),
            "ip": content.get("ip", ""),
            "domain": content.get("domain", ""),
            "description": content.get("description", ""),
            "weight": content.get("weight", ""),
            "threat_key": content.get("threat_key", ""),
        }
        rows.append(row)
    return rows


@click.group("threat-intel")
def threat_intel_group() -> None:
    """Manage ES threat-intelligence items (requires ES installed)."""


@threat_intel_group.command("list")
@click.option(
    "--type",
    "intel_type",
    type=click.Choice(_INTEL_TYPES),
    default=None,
    help="Filter by threat-intel collection type.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=100,
    help="Max results (default 100).",
)
@click.pass_context
def list_threat_intel(
    ctx: click.Context,
    intel_type: str | None,
    limit: int,
) -> None:
    """List threat-intelligence items, optionally filtered by type."""
    svc = _require_es(ctx)
    if svc is None:
        return

    kwargs: dict[str, Any] = {"output_mode": "json", "count": limit}
    if intel_type is not None:
        kwargs["threat_collection"] = intel_type

    resp = svc.get(_TI_ITEM_PATH, **kwargs)
    body: dict[str, Any] = json.loads(resp.body.read())
    rows = _parse_entries(body)
    output.render(ctx, rows, empty="No threat-intelligence items found.")


@threat_intel_group.command("upload")
@guard.guarded
@click.option(
    "--type",
    "intel_type",
    type=click.Choice(_INTEL_TYPES),
    required=True,
    help="Threat-intel collection type to upload into.",
)
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to a CSV or JSON file containing threat-intel items.",
)
@click.pass_context
def upload_threat_intel(
    ctx: click.Context,
    intel_type: str,
    file_path: str,
) -> None:
    """Upload threat-intelligence items from a local CSV or JSON file.

    The file is sent as multipart form data to
    ``/services/data/threat_intel/upload``.
    """
    path = Path(file_path)
    details = f"  type: {intel_type}\n  file: {path.name} ({path.stat().st_size} bytes)"
    if not guard.check(ctx, "Upload threat-intel items", details=details):
        return

    svc = _require_es(ctx)
    if svc is None:
        return

    file_bytes = path.read_bytes()
    # The SDK's post() doesn't support multipart, so we build the body
    # as the raw file content and pass the required fields as query params.
    resp = svc.post(
        _TI_UPLOAD_PATH,
        threat_collection=intel_type,
        filename=path.name,
        body=file_bytes,
        output_mode="json",
    )
    raw = resp.body.read()
    if raw:
        result: dict[str, Any] = json.loads(raw)
        count = len(result.get("entry", []))
        output.info(f"Uploaded threat-intel items to '{intel_type}' ({count} entries).")
    else:
        output.info(f"Uploaded threat-intel items to '{intel_type}'.")


@threat_intel_group.command("delete")
@guard.guarded
@click.argument("key")
@click.pass_context
def delete_threat_intel(ctx: click.Context, key: str) -> None:
    """Delete a threat-intelligence item by its key."""
    if not guard.check(ctx, f"Delete threat-intel item '{key}'"):
        return

    svc = _require_es(ctx)
    if svc is None:
        return

    svc.delete(f"{_TI_ITEM_PATH}/{key}", output_mode="json")
    output.info(f"Deleted threat-intel item '{key}'.")
