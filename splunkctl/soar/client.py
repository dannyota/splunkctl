"""SOAR REST API client — requests-based, lazy, normalizing.

Auth: ``ph-auth-token`` header preferred; automatic Basic fallback for
DELETE (server refuses tokens on DELETE except ``decided_list``).
Web UI session (cookie-based) used for operations the REST API lacks
(e.g. playbook deletion).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from typing import Any

import requests
import urllib3

from splunkctl.errors import kind_for_status

# Default (connect, read) timeout in seconds.  Override via
# SOAR_TIMEOUT env var (single int → both; "C,R" → connect, read).
_DEFAULT_TIMEOUT: tuple[int, int] = (10, 60)

_tls_warned: bool = False


def _warn_tls_off() -> None:
    """Emit a one-shot stderr warning when TLS verification is disabled."""
    global _tls_warned  # noqa: PLW0603
    if not _tls_warned:
        sys.stderr.write(
            "Warning: TLS certificate verification is disabled for SOAR"
            " (verify: false). Connections are susceptible to interception.\n"
        )
        _tls_warned = True


def _parse_timeout(raw: str) -> tuple[int, int] | int:
    """Parse a timeout string from the environment.

    Accepts ``"60"`` (both connect+read) or ``"10,60"`` (connect, read).
    """
    if "," in raw:
        parts = raw.split(",", maxsplit=1)
        return int(parts[0]), int(parts[1])
    return int(raw)


# Endpoints with non-standard envelopes.
_BARE_ARRAY_ENDPOINTS: frozenset[str] = frozenset({"audit"})
_RESULTS_ENVELOPE_ENDPOINTS: frozenset[str] = frozenset({"search"})

# DELETE endpoints that accept token auth (exceptions to the Basic rule).
_TOKEN_DELETE_OK: frozenset[str] = frozenset({"decided_list"})

# Operators where the value is not a string and should not be quoted.
_UNQUOTED_OPS: frozenset[str] = frozenset({"in", "range"})


class SOARError(Exception):
    """SOAR API error with ``errors.py``-compatible kind and status."""

    def __init__(  # noqa: D107
        self,
        message: str,
        *,
        kind: str = "error",
        http_status: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.kind = kind
        self.http_status = http_status
        self.data = data or {}
        super().__init__(message)


def build_filters(**kwargs: Any) -> dict[str, str]:
    """Build Django-style query-string filters for a SOAR REST call.

    Rules:
    - Strings are quoted (``"value"``).
    - Booleans become Python-style ``True``/``False``.
    - Integers/floats are unquoted.
    - ``__in`` lists serialize as ``[1, 2, 3]``.
    - Keys starting with ``_exclude_`` pass through as-is.
    - ``None`` values are skipped.
    """
    params: dict[str, str] = {}
    for key, value in kwargs.items():
        if value is None:
            continue

        if key.startswith("_exclude_"):
            params[key] = _format_value(key, value)
            continue

        # Split off operator suffix (e.g. name__icontains -> name, icontains)
        params[f"_filter_{key}"] = _format_value(key, value)

    return params


def _format_value(key: str, value: Any) -> str:
    """Format a filter value per SOAR conventions."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        inner = ", ".join(str(v) for v in value)
        return f"[{inner}]"
    if isinstance(value, int | float):
        return str(value)
    # String values: quote unless it's an __in/__range op
    parts = key.rsplit("__", maxsplit=1)
    op = parts[-1] if len(parts) > 1 else None
    if op in _UNQUOTED_OPS:
        return str(value)
    return f'"{value}"'


class SOARClient:
    """Lazy SOAR REST API client.

    No I/O happens until the first ``get``/``post``/``delete`` call.
    """

    def __init__(  # noqa: D107
        self,
        *,
        host: str,
        port: int = 8443,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify: bool = False,
        timeout: tuple[int, int] | int | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._token = token
        self._username = username
        self._password = password
        self._verify = verify
        self._session = requests.Session()
        self._session.verify = verify

        # Resolve timeout: kwarg > env var > default.
        env_timeout = os.environ.get("SOAR_TIMEOUT")
        if timeout is not None:
            self._timeout: tuple[int, int] | int = timeout
        elif env_timeout:
            self._timeout = _parse_timeout(env_timeout)
        else:
            self._timeout = _DEFAULT_TIMEOUT

        if not verify:
            # verify=false is an explicit config choice (lab/self-signed);
            # without this every request spams InsecureRequestWarning.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            _warn_tls_off()

        # Separate session for Django-view-only operations (e.g. delete).
        self._web_session: requests.Session | None = None
        self._web_csrf: str | None = None

    # -- URL helpers --------------------------------------------------------

    @property
    def _base_url(self) -> str:
        return f"https://{self._host}:{self._port}/rest"

    def _url(self, path: str) -> str:
        clean = path.lstrip("/")
        return f"{self._base_url}/{clean}"

    # -- Auth helpers -------------------------------------------------------

    def _token_headers(self) -> dict[str, str]:
        return {"ph-auth-token": self._token or ""}

    def _basic_auth(self) -> tuple[str, str]:
        return (self._username or "", self._password or "")

    def _has_basic(self) -> bool:
        return bool(self._username and self._password)

    def _auth_kwargs(self, *, method: str, path: str) -> dict[str, Any]:
        """Build auth kwargs for a request.

        DELETE uses Basic (server refuses tokens) except for decided_list.
        Everything else prefers token, falls back to Basic.
        """
        if method == "DELETE":
            endpoint_root = path.lstrip("/").split("/")[0]
            if endpoint_root not in _TOKEN_DELETE_OK:
                if not self._has_basic():
                    raise SOARError(
                        "delete requires username/password credentials "
                        "(SOAR refuses token auth on DELETE)",
                        kind="auth",
                    )
                return {"auth": self._basic_auth(), "headers": {}}
            # decided_list DELETE: token OK if available, else Basic
            if self._token:
                return {"headers": self._token_headers()}
            if self._has_basic():
                return {"auth": self._basic_auth(), "headers": {}}
            raise SOARError("No credentials configured", kind="auth")

        # Non-DELETE: prefer token, fall back to Basic
        if self._token:
            return {"headers": self._token_headers()}
        if self._has_basic():
            return {"auth": self._basic_auth(), "headers": {}}
        raise SOARError("No credentials configured", kind="auth")

    # -- Request helpers ----------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: str | None = None,
    ) -> Any:
        """Execute a request and return the parsed, normalized JSON."""
        auth_kw = self._auth_kwargs(method=method, path=path)
        headers: dict[str, str] = auth_kw.get("headers", {})
        if data is not None:
            headers["Content-Type"] = "application/json"

        kwargs: dict[str, Any] = {
            "method": method,
            "url": self._url(path),
            "headers": headers,
            "params": params,
            "timeout": self._timeout,
        }
        if data is not None:
            kwargs["data"] = data
        if "auth" in auth_kw:
            kwargs["auth"] = auth_kw["auth"]

        resp: requests.Response = self._session.request(**kwargs)
        return self._handle_response(resp, path=path, method=method)

    def _handle_response(
        self,
        resp: requests.Response,
        *,
        path: str,
        method: str,
    ) -> Any:
        """Parse JSON, check for errors, normalize envelope."""
        try:
            body: Any = resp.json()
        except (ValueError, json.JSONDecodeError):
            if resp.status_code >= 400:
                raise SOARError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                    kind=kind_for_status(resp.status_code),
                    http_status=resp.status_code,
                ) from None
            return {}

        # Check for failed:true (can appear on any status code)
        if isinstance(body, dict) and body.get("failed"):
            msg = body.get("message", f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                kind = kind_for_status(resp.status_code)
                http_status: int | None = resp.status_code
            else:
                # Logical failure on HTTP 200 — not an HTTP error
                kind = "error"
                http_status = None
            raise SOARError(
                msg,
                kind=kind,
                http_status=http_status,
                data=body,
            )

        # HTTP errors without failed:true
        if resp.status_code >= 400:
            msg = (
                body.get("message", f"HTTP {resp.status_code}")
                if isinstance(body, dict)
                else f"HTTP {resp.status_code}"
            )
            raise SOARError(
                msg,
                kind=kind_for_status(resp.status_code),
                http_status=resp.status_code,
            )

        # Normalize response envelope for GET list endpoints
        if method == "GET":
            body = self._normalize_get_envelope(body, path)

        # Normalize POST response keys
        if method == "POST" and isinstance(body, dict):
            body = self._normalize_post_keys(body)

        return body

    def _normalize_get_envelope(self, body: Any, path: str) -> Any:
        """Normalize GET list responses to {count, num_pages, data}."""
        endpoint_root = path.lstrip("/").split("/")[0]

        # Bare array (audit)
        if isinstance(body, list):
            return {"count": len(body), "num_pages": 1, "data": body}

        if not isinstance(body, dict):
            return body

        # {results} envelope (search) — server paginates (1-based pages)
        # and returns real num_pages; forward it instead of hardcoding 1.
        if endpoint_root in _RESULTS_ENVELOPE_ENDPOINTS and "results" in body:
            results = body["results"]
            count = body.get("count", len(results))
            num_pages = body.get("num_pages", 1)
            return {"count": count, "num_pages": num_pages, "data": results}

        return body

    @staticmethod
    def _normalize_post_keys(body: dict[str, Any]) -> dict[str, Any]:
        """Normalize response keys to canonical forms.

        Mappings:
            ``succeeded`` -> ``success``
            ``action_run_id`` -> ``id``
            ``playbook_run_id`` -> ``id``
        """
        if "succeeded" in body and "success" not in body:
            body["success"] = body.pop("succeeded")
        if "action_run_id" in body and "id" not in body:
            body["id"] = body.pop("action_run_id")
        if "playbook_run_id" in body and "id" not in body:
            body["id"] = body.pop("playbook_run_id")
        return body

    # -- Web UI session (Django views) ----------------------------------------

    def web_delete_playbooks(self, ids: list[int]) -> dict[str, Any]:
        """Delete playbooks via the Django Web UI handler (see soar/web.py)."""
        from splunkctl.soar import web

        return web.delete_playbooks(self, ids)

    # -- Public API ---------------------------------------------------------

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET a SOAR REST endpoint. Returns normalized envelope."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        body: Any,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """POST to a SOAR REST endpoint. Accepts dict or list body."""
        data = json.dumps(body)
        return self._request("POST", path, params=params, data=data)

    def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """DELETE a SOAR REST endpoint. Uses Basic auth (except decided_list)."""
        return self._request("DELETE", path, params=params)

    def get_bytes(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        """GET a SOAR REST endpoint and return raw bytes.

        Used for binary downloads (e.g. ``download_attachment``).
        Raises :class:`SOARError` on non-2xx responses.
        """
        auth_kw = self._auth_kwargs(method="GET", path=path)
        headers: dict[str, str] = auth_kw.get("headers", {})

        kwargs: dict[str, Any] = {
            "method": "GET",
            "url": self._url(path),
            "headers": headers,
            "params": params,
            "timeout": self._timeout,
        }
        if "auth" in auth_kw:
            kwargs["auth"] = auth_kw["auth"]

        resp: requests.Response = self._session.request(**kwargs)
        if resp.status_code >= 400:
            raise SOARError(
                f"HTTP {resp.status_code}: {resp.text[:200]}",
                kind=kind_for_status(resp.status_code),
                http_status=resp.status_code,
            )
        return resp.content

    def iter_pages(
        self,
        path: str,
        *,
        page_size: int = 100,
        params: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate all items across paginated results.

        Yields individual items from each page, transparently fetching
        subsequent pages as needed.

        Pagination origin varies by endpoint:
        - ``search`` (``_RESULTS_ENVELOPE_ENDPOINTS``): 1-based pages.
        - All other endpoints: 0-based pages.
        """
        endpoint_root = path.lstrip("/").split("/")[0]
        origin = 1 if endpoint_root in _RESULTS_ENVELOPE_ENDPOINTS else 0
        page = origin
        while True:
            page_params = dict(params or {})
            page_params["page"] = page
            page_params["page_size"] = page_size

            result = self.get(path, params=page_params)
            data: list[dict[str, Any]] = result.get("data", [])
            yield from data

            num_pages = result.get("num_pages", 1)
            page += 1
            if page - origin >= num_pages or not data:
                break
