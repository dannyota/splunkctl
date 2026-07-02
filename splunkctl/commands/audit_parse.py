"""Normalize both index=_audit event shapes into one six-key schema.

Splunk ships two incompatible shapes in the same ``_audit`` index, mixed
in one stream:

- ``audittrail`` (legacy): a plain-text line,
  ``Audit:[timestamp=..., user=..., action=..., <tail>]`` where
  ``<tail>`` is an action-specific, comma-separated list of extra fields
  (e.g. ``info=granted, cap=1`` for capability checks,
  ``modified_settings=[...]`` for ``edit_index``, or no ``info=`` at all
  for some system actions like ``artifact_deleted``/file-integrity
  ``update`` — confirmed live). Only ``timestamp``/``user``/``action``
  are structurally guaranteed; there is no field that consistently
  identifies "the object" across every action. Many admin-capability
  checks (``edit_user``, ``edit_roles``, ...) do carry a literal
  ``object="..."`` marker, so that's used when present.
- ``audittrailv2`` (structured): one JSON object per line, with
  ``actor.name``, a top-level ``action``, and a ``data`` object shaped
  ``{name, type, ownership: {app, owner}, attributes}`` for
  object/system-category events (config changes), or just
  ``{type, attributes}`` / ``{attributes}`` for action/authn/check
  events (searches, logins, capability checks). There is no literal
  ``data.object``/``data.object_type`` key on real events — ``data.name``
  and ``data.type`` are the nearest equivalents and are used here.

Both are normalized into the same six-key schema so callers never
hand-write shape-specific parsing. An event matching neither shape is
never dropped — it comes back with ``action: "unparsed"`` and the raw
line preserved in ``object``, so audit evidence stays complete.
"""

import json
import re
from typing import Any

SCHEMA_KEYS: tuple[str, ...] = (
    "time",
    "user",
    "action",
    "object",
    "object_type",
    "app",
)

_LEGACY_RE = re.compile(
    r"^Audit:\[timestamp=(?P<timestamp>[^,]*),\s*"
    r"user=(?P<user>[^,]*),\s*"
    r"action=(?P<action>[^,\]]*)"
)
_OBJECT_RE = re.compile(r'object="(?P<value>[^"]*)"')
_APP_RE = re.compile(r'app=(?:"(?P<quoted>[^"]*)"|(?P<bare>[^,\]]+))')


def _as_str(value: Any) -> str:
    """Coerce a JSON scalar (or ``None``) to ``str`` for the output schema."""
    return "" if value is None else str(value)


def _event_time(row: dict[str, Any]) -> str:
    """Splunk's own indexed ``_time`` — present on every event regardless of shape.

    Used instead of re-parsing the two different embedded timestamp
    formats: it's always populated (Splunk's own ``TIME_FORMAT``
    extraction already did that work at index time) and gives one
    consistent, sortable representation across both shapes.
    """
    return _as_str(row.get("_time"))


def _parse_json_shape(raw: str) -> dict[str, str] | None:
    """Parse the structured JSON shape (sourcetype ``audittrailv2``).

    Returns ``None`` when ``raw`` isn't valid JSON or doesn't look like an
    audittrailv2 event (missing ``actor``/``action``), so the caller can
    fall back to the legacy parser.
    """
    try:
        obj: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(obj, dict) or "action" not in obj or "actor" not in obj:
        return None

    actor = obj.get("actor")
    user = actor.get("name") if isinstance(actor, dict) else None

    data = obj.get("data")
    data = data if isinstance(data, dict) else {}
    ownership = data.get("ownership")
    ownership = ownership if isinstance(ownership, dict) else {}
    attributes = data.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    app = ownership.get("app") or attributes.get("app")

    return {
        "user": _as_str(user),
        "action": _as_str(obj.get("action")),
        "object": _as_str(data.get("name")),
        "object_type": _as_str(data.get("type")),
        "app": _as_str(app),
    }


def _parse_legacy_shape(raw: str) -> dict[str, str] | None:
    """Parse the legacy plain-text shape (sourcetype ``audittrail``).

    Returns ``None`` when ``raw`` doesn't match the
    ``Audit:[timestamp=..., user=..., action=...`` prefix, so the caller
    can fall back to the unparsed case.
    """
    m = _LEGACY_RE.match(raw)
    if m is None:
        return None

    obj_m = _OBJECT_RE.search(raw)
    app_m = _APP_RE.search(raw)
    app = ""
    if app_m is not None:
        app = (
            app_m.group("quoted")
            if app_m.group("quoted") is not None
            else app_m.group("bare")
        )

    return {
        "user": m.group("user").strip(),
        "action": m.group("action").strip(),
        "object": obj_m.group("value") if obj_m is not None else "",
        "object_type": "",
        "app": app.strip(),
    }


def parse_event(row: dict[str, Any]) -> dict[str, str]:
    """Normalize one raw ``_audit`` result row into the six-key schema.

    Tries the JSON shape, then the legacy text shape; anything matching
    neither becomes an ``action: "unparsed"`` row with the full raw line
    in ``object`` — never silently dropped.
    """
    raw = _as_str(row.get("_raw"))
    parsed = _parse_json_shape(raw) or _parse_legacy_shape(raw)
    if parsed is None:
        parsed = {
            "user": "",
            "action": "unparsed",
            "object": raw,
            "object_type": "",
            "app": "",
        }
    return {"time": _event_time(row), **parsed}
