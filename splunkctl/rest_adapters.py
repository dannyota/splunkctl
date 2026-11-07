"""Local REST entities for endpoints absent from the upstream SDK."""

from __future__ import annotations

from typing import Any, ClassVar

from splunklib.binding import HTTPError, UrlEncoded


def _segment(value: str) -> Any:
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
        collection: _Collection,
        entry: dict[str, Any],
        *,
        owner: str | None = None,
        app: str | None = None,
    ) -> None:
        self.name: str = entry["name"]
        self.content = _Record(entry["content"])
        self.access = _Record(entry.get("acl", self.content.get("eai:acl", {})))
        self._service = collection.service
        self._path = collection.path + "/" + _segment(self.name)
        if owner is None and app is None:
            owner = self._service.namespace.get("owner")
            app = self._service.namespace.get("app")
        self._owner = self.access.get("owner", owner)
        self._app = self.access.get("app", app)

    def update(self, **fields: Any) -> None:
        """Post form fields in the entity's resolved namespace."""
        self._service.post(
            self._path,
            owner=_segment(self._owner) if self._owner is not None else None,
            app=_segment(self._app) if self._app is not None else None,
            **fields,
        )

    def delete(self) -> None:
        """Delete this entity in its resolved namespace."""
        self._service.delete(
            self._path,
            owner=_segment(self._owner) if self._owner is not None else None,
            app=_segment(self._app) if self._app is not None else None,
        )

    def acl_update(self, **fields: Any) -> None:
        """Post ACL fields without confusing form owner with namespace owner."""
        # The SDK reserves owner/app kwargs for routing, so put the namespace
        # in the path and leave the ACL's owner in the form body.
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
            + "/acl"
        )
        self._service.post(path, body=fields)


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

    def enable(self) -> None:
        """Enable this input."""
        self.update(disabled="0")

    def disable(self) -> None:
        """Disable this input."""
        self.update(disabled="1")


class _Collection:
    """JSON collection using the existing SDK's authenticated transport."""

    path: ClassVar[str]
    entity_type: ClassVar[type[_Entity]]

    def __init__(self, service: Any) -> None:
        self.service = service

    def list(
        self, *, owner: str | None = None, app: str | None = None, **query: Any
    ) -> list[Any]:
        """List entries in server order; omitted count fetches all entries."""
        from splunkctl.client import rest_get_json

        query.setdefault("count", 0)
        body = rest_get_json(self.service, self.path, owner=owner, app=app, **query)
        return [
            self.entity_type(self, entry, owner=owner, app=app)
            for entry in _entries(body)
        ]

    def _get(
        self, name: str, *, owner: str | None = None, app: str | None = None
    ) -> Any:
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
        return self.entity_type(self, entries[0], owner=owner, app=app)

    def __getitem__(self, name: str) -> Any:
        return self._get(name)

    def _create(
        self,
        name: str,
        *,
        owner: str | None = None,
        app: str | None = None,
        **fields: Any,
    ) -> Any:
        """Create with form parameters and read the resolved entity metadata."""
        self.service.post(self.path, owner=owner, app=app, name=name, **fields)
        return self._get(name, owner=owner, app=app)


class Dashboards(_Collection):
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
    ) -> Any:
        """Create a view from its XML definition."""
        return super()._create(
            name, owner=owner, app=app, **{"eai:data": data, **fields}
        )


class LookupTableFiles(_Collection):
    """Lookup file metadata collection."""

    path = "data/lookup-table-files"
    entity_type = LookupTableFile


class HECTokens(_Collection):
    """HEC inputs accepting both bare and http-prefixed names."""

    path = "data/inputs/http"
    entity_type = HECToken

    def create(self, name: str, **fields: Any) -> Any:
        """Create an HTTP input from form fields."""
        return self._create(name, **fields)

    def _get(
        self, name: str, *, owner: str | None = None, app: str | None = None
    ) -> Any:
        try:
            return super()._get(name, owner=owner, app=app)
        except _MissingEntity:
            alias = (
                name.removeprefix("http://")
                if name.startswith("http://")
                else "http://" + name
            )
            return super()._get(alias, owner=owner, app=app)
