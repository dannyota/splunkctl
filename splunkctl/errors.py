"""Shared exception -> error-envelope classification.

``splunkctl.main._CLI.invoke`` uses this to classify exceptions escaping
any command into the ``output.error`` kind/http_status taxonomy. Commands
that do their own try/except around client calls (e.g. ``config test``,
which needs to keep running after a failed connectivity check) reuse the
same mapping so every failure path lands on one taxonomy.
"""

from typing import NamedTuple

import requests


class WebSessionError(RuntimeError):
    """Failure in a Splunk Web UI session (login, CSRF, upload).

    Carries a ``kind`` so ``classify`` can map it to a clean error
    envelope without falling through to the unclassified re-raise path.
    """

    def __init__(self, message: str, *, kind: str = "auth") -> None:  # noqa: D107
        super().__init__(message)
        self.message = message
        self.kind = kind


_HTTP_KIND: dict[int, str] = {
    401: "auth",
    403: "permission",
    404: "not_found",
    409: "conflict",
}


def kind_for_status(status: int | None) -> str:
    """Map an HTTP status code to an error envelope kind.

    Any HTTP error not in ``_HTTP_KIND`` maps to the generic ``http`` kind.
    """
    if status is None:
        return "http"
    return _HTTP_KIND.get(status, "http")


class Classified(NamedTuple):
    """A classified exception, ready to pass to ``output.error(**_)``."""

    message: str
    kind: str
    http_status: int | None


def classify(exc: Exception) -> Classified | None:
    """Classify ``exc`` into a message/kind/http_status triple.

    Returns ``None`` for exception types this taxonomy doesn't cover —
    callers should fall back to their own default handling (e.g. an
    unclassified ``error`` kind, or re-raising).
    """
    # WebSessionError carries kind natively (auth/web).
    if isinstance(exc, WebSessionError):
        return Classified(exc.message, exc.kind, None)

    # SOARError carries kind/http_status natively — pass through.
    from splunkctl.soar.client import SOARError

    if isinstance(exc, SOARError):
        return Classified(exc.message, exc.kind, exc.http_status)

    name = type(exc).__name__
    if name == "HTTPError":
        status: int | None = getattr(exc, "status", None)
        msg = str(exc)
        kind = kind_for_status(status)
        if status == 403:
            return Classified(f"Permission denied: {msg}", kind, status)
        if status == 401:
            return Classified(f"Authentication failed: {msg}", kind, status)
        if status == 404:
            return Classified(f"Not found: {msg}", kind, status)
        return Classified(msg, kind, status)
    if name == "AuthenticationError":
        status = getattr(exc, "status", None)
        return Classified(f"Authentication failed: {exc}", "auth", status)
    # requests exceptions subclass OSError (via IOError), so they must be
    # checked ahead of the plain TimeoutError/OSError fallbacks below —
    # otherwise a requests.exceptions.Timeout would be misclassified as a
    # generic "connection" failure instead of "timeout".
    if isinstance(exc, requests.exceptions.Timeout):
        return Classified(str(exc), "timeout", None)
    if isinstance(exc, requests.exceptions.ConnectionError):
        return Classified(str(exc), "connection", None)
    if isinstance(exc, requests.exceptions.RequestException):
        return Classified(str(exc), "connection", None)
    if isinstance(exc, TimeoutError):
        return Classified(str(exc), "timeout", None)
    if isinstance(exc, OSError):
        return Classified(str(exc), "connection", None)
    return None
