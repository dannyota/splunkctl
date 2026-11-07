"""Local REST entities for endpoints absent from the upstream SDK."""

from __future__ import annotations

import json
from typing import Any, ClassVar, Self

from splunklib.binding import HTTPError, UrlEncoded


def _segment(value: str) -> UrlEncoded:
    """Encode one path segment, preserving spaces as path escapes."""
    encoded = UrlEncoded(value, encode_slash=True)
    return UrlEncoded(str(encoded).replace("+", "%20"), skip_encode=True)


class _MissingEntity(KeyError):
    """An absent entry, distinct from malformed JSON metadata."""


def _entries(body: Any) -> list[dict[str, Any]]:
    """Validate response structure so malformed entries cannot mean missing."""
    if not isinstance(body, dict) or not isinstance(body.get("entry"), list):
        raise ValueError("Malformed REST response: expected entry list")
    entries: list[dict[str, Any]] = body["entry"]
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not isinstance(entry.get("content"), dict)
        ):
            raise ValueError("Malformed REST response: expected entry name/content")
        acl = entry.get("acl", entry["content"].get("eai:acl", {}))
        if not isinstance(acl, dict):
            raise ValueError("Malformed REST response: expected ACL mapping")
    return entries


class _Record(dict[str, Any]):
    """REST fields supporting the SDK's mapping and attribute conventions."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class _Entity:
    """An entry bound to its resolved namespace."""

    def __init__(
        self,
        service: Any,
        path: str,
        entry: dict[str, Any],
        *,
        owner: str | None = None,
        app: str | None = None,
    ) -> None:
        self._service = service
        self._collection_path = path
        self._load(entry, owner=owner, app=app)

    def _load(
        self, entry: dict[str, Any], *, owner: str | None, app: str | None
    ) -> None:
        self.name: str = entry["name"]
        self.content = _Record(entry["content"])
        self.access = _Record(entry.get("acl", self.content.get("eai:acl", {})))
        self._path = self._collection_path + "/" + _segment(self.name)
        alternate = entry.get("links", {}).get("alternate")
        self._alternate = UrlEncoded(alternate, skip_encode=True) if alternate else None
        if owner is None and app is None:
            owner = self._service.namespace.get("owner")
            app = self._service.namespace.get("app")
        self._owner = self.access.get("owner", owner)
        self._app = self.access.get("app", app)

    def _routing(self) -> dict[str, str | None]:
        if self._alternate is not None:
            return {}
        return {
            "owner": _segment(self._owner) if self._owner is not None else None,
            "app": _segment(self._app) if self._app is not None else None,
        }

    def _refresh(self) -> Self:
        response = self._service.get(
            self._alternate or self._path, output_mode="json", **self._routing()
        )
        entries = _entries(json.loads(response.body.read()))
        if not entries:
            raise _MissingEntity(self.name)
        self._load(entries[0], owner=self._owner, app=self._app)
        return self

    def update(self, **fields: Any) -> Self:
        """Post form fields to the server's canonical entity path."""
        if "name" in fields:
            raise ValueError("renaming is not supported")
        self._service.post(self._alternate or self._path, **self._routing(), **fields)
        return self

    def delete(self) -> None:
        """Delete this entity using its canonical path when available."""
        self._service.delete(self._alternate or self._path, **self._routing())

    def acl_update(self, **fields: Any) -> Self:
        """Post ACL fields without confusing form owner with namespace owner."""
        path = self._alternate
        if path is None:
            namespace = self._service.namespace
            owner = self._owner or namespace.get("owner") or "nobody"
            app = self._app or namespace.get("app") or "search"
            path = (
                "/servicesNS/"
                + _segment(owner)
                + "/"
                + _segment(app)
                + "/"
                + self._path
            )
        self._service.post(path + "/acl", body=fields)
        return self._refresh()


class Dashboard(_Entity):
    """A dashboard view and its XML definition."""

    def export(self) -> str:
        """Return the original XML, including Studio's embedded definition."""
        value = self.content.get("eai:data")
        if not isinstance(value, str):
            raise ValueError("Malformed dashboard: expected eai:data string")
        return value


class LookupTableFile(_Entity):
    """Lookup metadata; content transfer remains in the command layer."""


class HECToken(_Entity):
    """An HTTP Event Collector input."""

    def enable(self) -> Self:
        """Enable this input."""
        self.update(disabled="0")
        return self._refresh()

    def disable(self) -> Self:
        """Disable this input."""
        self.update(disabled="1")
        return self._refresh()


class _Collection[E: _Entity]:
    """JSON collection using the existing SDK's authenticated transport."""

    path: ClassVar[str]
    entity_type: type[E]

    def __init__(self, service: Any) -> None:
        self.service = service

    def list(
        self, *, owner: str | None = None, app: str | None = None, **query: Any
    ) -> list[E]:
        """List entries in server order; omitted count fetches all entries."""
        from splunkctl.client import rest_get_json

        query.setdefault("count", 0)
        body = rest_get_json(self.service, self.path, owner=owner, app=app, **query)
        return [
            self.entity_type(self.service, self.path, entry, owner=owner, app=app)
            for entry in _entries(body)
        ]

    def _get(self, name: str, *, owner: str | None = None, app: str | None = None) -> E:
        from splunkctl.client import rest_get_json

        path = self.path + "/" + _segment(name)
        if owner is None and app is None:
            owner = self.service.namespace.get("owner")
            app = self.service.namespace.get("app")
        try:
            body = rest_get_json(
                self.service,
                path,
                owner=_segment(owner) if owner is not None else None,
                app=_segment(app) if app is not None else None,
            )
        except HTTPError as exc:
            if exc.status == 404:
                raise _MissingEntity(name) from exc
            raise
        entries = _entries(body)
        if not entries:
            raise _MissingEntity(name)
        return self.entity_type(
            self.service, self.path, entries[0], owner=owner, app=app
        )

    def __getitem__(self, name: str) -> E:
        return self._get(name)

    def _create(
        self,
        name: str,
        *,
        owner: str | None = None,
        app: str | None = None,
        **fields: Any,
    ) -> E:
        """Create with form parameters and read the resolved entity metadata."""
        self.service.post(self.path, owner=owner, app=app, name=name, **fields)
        return self._get(name, owner=owner, app=app)


class Dashboards(_Collection[Dashboard]):
    """Dashboard views collection."""

    path = "data/ui/views"
    entity_type = Dashboard

    def create(
        self,
        name: str,
        data: str,
        *,
        owner: str | None = None,
        app: str | None = None,
        **fields: Any,
    ) -> Dashboard:
        """Create a view from its XML definition."""
        return super()._create(
            name, owner=owner, app=app, **{"eai:data": data, **fields}
        )


class LookupTableFiles(_Collection[LookupTableFile]):
    """Lookup file metadata collection."""

    path = "data/lookup-table-files"
    entity_type = LookupTableFile


class HECTokens(_Collection[HECToken]):
    """HEC inputs accepting both bare and http-prefixed names."""

    path = "data/inputs/http"
    entity_type = HECToken

    def create(self, name: str, **fields: Any) -> HECToken:
        """Create an HTTP input from form fields."""
        return self._create(name, **fields)

    def _get(
        self, name: str, *, owner: str | None = None, app: str | None = None
    ) -> HECToken:
        try:
            return super()._get(name, owner=owner, app=app)
        except _MissingEntity:
            alias = (
                name.removeprefix("http://")
                if name.startswith("http://")
                else "http://" + name
            )
            return super()._get(alias, owner=owner, app=app)
