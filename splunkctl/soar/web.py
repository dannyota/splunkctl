"""SOAR Django Web UI session — operations the REST API lacks.

Playbook deletion has no working REST route on SOAR 8.5
(``DELETE /rest/playbook/<id>`` → 405; ``POST`` with
``{"delete": true}`` → silent no-op), so the client logs into the Web
UI the way a browser does (csrftoken cookie + AJAX login) and posts
the same request the ``/playbooks`` page sends. Requires
username/password — the Web UI refuses token auth.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import requests

from splunkctl.errors import kind_for_status

if TYPE_CHECKING:
    from splunkctl.soar.client import SOARClient


def ensure_web_login(client: SOARClient) -> requests.Session:
    """Authenticate to the SOAR Django Web UI (cookie-based session).

    The session and CSRF token are cached on *client* — repeated calls
    reuse the login. Raises :class:`SOARError` (kind ``auth``) without
    username/password credentials or on a refused login.
    """
    from splunkctl.soar.client import SOARError

    if client._web_session is not None:  # noqa: SLF001
        return client._web_session  # noqa: SLF001

    # Browser-mode clients already hold a Django session; reuse it instead of
    # attempting username/password login (which browser profiles don't have).
    if client._cookies:  # noqa: SLF001
        sess = requests.Session()
        sess.verify = client._verify  # noqa: SLF001
        for name, value in client._cookies.items():  # noqa: SLF001
            sess.cookies.set(name, value)
        client._web_csrf = client._cookies.get("csrftoken", "")  # noqa: SLF001
        client._web_session = sess  # noqa: SLF001
        return sess

    if not client._has_basic():  # noqa: SLF001
        raise SOARError(
            "Playbook deletion requires username/password credentials "
            "(the SOAR Web UI does not accept token auth).",
            kind="auth",
        )

    sess = requests.Session()
    sess.verify = client._verify  # noqa: SLF001
    base = f"https://{client._host}:{client._port}"  # noqa: SLF001

    # GET login page to obtain csrftoken cookie.
    sess.get(f"{base}/login", timeout=15)
    csrf = sess.cookies.get("csrftoken")
    if not csrf:
        raise SOARError(
            "Could not obtain CSRF token from SOAR login page.",
            kind="error",
        )

    # POST login (AJAX-style).
    resp = sess.post(
        f"{base}/login",
        data={
            "username": client._username,  # noqa: SLF001
            "password": client._password,  # noqa: SLF001
        },
        headers={
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{base}/login",
        },
        timeout=15,
    )
    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        raise SOARError(
            f"SOAR Web login failed: HTTP {resp.status_code}",
            kind="auth",
            http_status=resp.status_code,
        ) from None
    if not body.get("authenticated"):
        raise SOARError(
            "SOAR Web login failed: invalid credentials.",
            kind="auth",
        )

    client._web_csrf = sess.cookies.get("csrftoken") or csrf  # noqa: SLF001
    client._web_session = sess  # noqa: SLF001
    return sess


def delete_playbooks(client: SOARClient, ids: list[int]) -> dict[str, Any]:
    """Delete playbooks via the Django Web UI handler.

    Uses the same route the browser calls (``POST /playbooks`` with
    ``{ids, delete: true}``). The handler answers with a
    ``{done_count, fail_count, changes, errors}`` envelope (captured
    live on SOAR 8.5); anything else raises rather than being misread
    as "nothing deleted".
    """
    from splunkctl.soar.client import SOARError

    sess = ensure_web_login(client)
    base = f"https://{client._host}:{client._port}"  # noqa: SLF001

    resp = sess.post(
        f"{base}/playbooks",
        json={"ids": ids, "delete": True},
        headers={
            "X-CSRFToken": client._web_csrf or "",  # noqa: SLF001
            "Referer": f"{base}/playbooks",
        },
        timeout=30,
    )

    try:
        body: dict[str, Any] = resp.json()
    except (ValueError, json.JSONDecodeError):
        raise SOARError(
            f"Playbook delete failed: HTTP {resp.status_code}",
            kind=kind_for_status(resp.status_code),
            http_status=resp.status_code,
        ) from None

    if resp.status_code >= 400 or body.get("failed"):
        msg = body.get("message", f"HTTP {resp.status_code}")
        is_http_err = resp.status_code >= 400
        raise SOARError(
            msg,
            kind=kind_for_status(resp.status_code) if is_http_err else "error",
            http_status=resp.status_code if is_http_err else None,
        )

    if "done_count" not in body and "fail_count" not in body:
        raise SOARError(
            "Unexpected response from the SOAR Web UI delete handler "
            f"(no done_count/fail_count): {str(body)[:200]}",
            kind="error",
        )
    return body
