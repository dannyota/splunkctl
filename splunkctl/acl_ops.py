"""Shared ACL resolution, rendering and canonical-path updates."""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import click
from splunklib.binding import HTTPError, UrlEncoded

from splunkctl.client import rest_get_json
from splunkctl.errors import WebSessionError
from splunkctl.rest_adapters import _segment

RESOURCES = {
    "saved-search": "saved/searches",
    "macro": "configs/conf-macros",
    "eventtype": "configs/conf-eventtypes",
    "tag": "configs/conf-tags",
    "props": "configs/conf-props",
    "transform": "configs/conf-transforms",
    "lookup-definition": "data/transforms/lookups",
    "lookup-table": "data/lookup-table-files",
    "field-extraction": "data/props/extractions",
    "data-model": "datamodel/model",
    "view": "data/ui/views",
    "dashboard": "data/ui/views",
}


def one(body: dict[str, Any]) -> dict[str, Any]:
    """Require one resolved entry, refusing ambiguous namespaces."""
    entries = body.get("entry", [])
    if not entries:
        raise WebSessionError("Object not found", kind="not_found")
    if len(entries) != 1:
        raise WebSessionError(
            "Ambiguous object; specify --app and owner", kind="conflict"
        )
    return dict(entries[0])


def canonical(entry: dict[str, Any]) -> UrlEncoded:
    """Use the server's new namespace without following its origin host."""
    target = entry.get("links", {}).get("alternate") or entry.get("id")
    if not target:
        raise WebSessionError("ACL response has no canonical entry path", kind="http")
    return UrlEncoded(urlsplit(str(target)).path, skip_encode=True)


def _datamodel_owners(svc: Any) -> Iterator[str]:
    """Try the configured namespace before looking up the authenticated user."""
    configured = svc.namespace.get("owner")
    if configured and configured != "-":
        yield configured
    context = rest_get_json(svc, "/services/authentication/current-context")
    yield context["entry"][0]["content"]["username"]
    yield "nobody"


def resolve(
    svc: Any, object_type: str, name: str, *, app: str | None, owner: str | None
) -> dict[str, Any]:
    """Fetch an exact encoded name in the selected namespace."""
    if object_type == "data-model" and owner is None:
        seen = set()
        for candidate in _datamodel_owners(svc):
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return resolve(svc, object_type, name, app=app, owner=candidate)
            except HTTPError as exc:
                if exc.status != 404 and not (
                    exc.status == 500
                    and "Cannot get username when all users are selected" in str(exc)
                ):
                    raise
            except WebSessionError as exc:
                if exc.kind != "not_found":
                    raise
        raise WebSessionError(
            "Object not found; pass --current-owner", kind="not_found"
        )
    namespace = svc.namespace
    selected_owner = owner if owner is not None else namespace.get("owner") or "-"
    selected_app = app if app is not None else namespace.get("app") or "search"
    path = (
        "/servicesNS/"
        + _segment(selected_owner)
        + "/"
        + _segment(selected_app)
        + "/"
        + RESOURCES[object_type]
        + "/"
        + _segment(name)
    )
    return one(rest_get_json(svc, path, count=0))


def row(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep role arrays and private null permissions intact."""
    acl = entry["acl"]
    perms = acl.get("perms") or {}
    result = {"name": entry["name"]}
    result.update({key: acl.get(key) for key in ("owner", "sharing", "app")})
    result.update({"read": perms.get("read"), "write": perms.get("write")})
    result.update(
        {
            key: acl.get(key)
            for key in (
                "modifiable",
                "can_change_perms",
                "can_share_user",
                "can_share_app",
                "can_share_global",
                "can_write",
                "can_list",
                "removable",
            )
        }
    )
    return result


def roles(value: str | None) -> list[str] | None:
    """An empty option clears; omission preserves; duplicates normalize."""
    if value is None:
        return None
    return list(dict.fromkeys(r.strip() for r in value.split(",") if r.strip()))


def changes(
    svc: Any,
    entry: dict[str, Any],
    *,
    sharing: str | None,
    owner: str | None,
    read: str | None,
    write: str | None,
) -> dict[str, Any]:
    """Validate requested roles before any write and build effective ACL fields."""
    current = row(entry)
    effective = sharing or current["sharing"]
    read_roles, write_roles = roles(read), roles(write)
    if effective == "user" and (read is not None or write is not None):
        raise click.UsageError("--read/--write require app or global sharing")
    requested = [*(read_roles or []), *(write_roles or [])]
    if requested:
        body = rest_get_json(svc, "/services/authorization/roles", count=0)
        known = {e["name"] for e in body.get("entry", [])}
        for role in requested:
            if role != "*" and role not in known:
                raise click.UsageError(f"Unknown role: {role}")
    fields = {
        "owner": owner if owner is not None else current["owner"],
        "sharing": effective,
    }
    if read is not None or write is not None:
        final_read = read_roles if read_roles is not None else current["read"] or []
        final_write = write_roles if write_roles is not None else current["write"] or []
        if not final_read and not final_write:
            raise click.UsageError("Splunk cannot clear both permission lists")
        for key, value in (("read", final_read), ("write", final_write)):
            if value:
                fields["perms." + key] = ",".join(value)
    if "/saved/searches/" in str(canonical(entry)):
        fields["app"] = current["app"]
    return fields


def unchanged(entry: dict[str, Any], fields: dict[str, Any]) -> bool:
    """Compare effective form fields to the current ACL."""
    current = row(entry)
    if any(key.startswith("perms.") for key in fields):
        if any(
            set(roles(fields.get("perms." + key)) or []) != set(current[key] or [])
            for key in ("read", "write")
        ):
            return False
    return all(
        (set(roles(str(value)) or []) == set(current[key[6:]] or []))
        if key.startswith("perms.")
        else current.get(key) == value
        for key, value in fields.items()
    )


def update(svc: Any, entry: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """POST then read back through the returned canonical namespace."""
    response = svc.post(canonical(entry) + "/acl", body=fields, output_mode="json")
    posted = one(json.loads(response.body.read()))
    confirmed = one(rest_get_json(svc, canonical(posted)))
    if not unchanged(confirmed, fields):
        raise WebSessionError(
            "ACL read-back does not match requested permissions", kind="conflict"
        )
    return confirmed
