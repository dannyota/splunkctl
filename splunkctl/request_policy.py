"""Method-based server mutation policy, applied at final dispatch."""

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from splunkctl.request_context import current, readonly


class ReadOnlyError(RuntimeError):
    """A request or command violates server read-only protection."""

    def __init__(self, message: str) -> None:
        """Prefix policy failures for a stable error envelope."""
        super().__init__(
            message if message.startswith("read-only:") else f"read-only: {message}"
        )


def origin(url: str) -> tuple[str, str | None, int | None]:
    """Normalize an origin, including its default port."""
    parsed = urlsplit(url)
    return (
        parsed.scheme.lower(),
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def canonical_path(url: str) -> str:
    """Decode routing syntax conservatively before classification."""
    path = urlsplit(url).path
    for _ in range(8):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    if "%" in path or "\\" in path or any(ord(c) < 32 for c in path):
        raise ReadOnlyError("ambiguous request path")
    segments = path.split("/")
    if any(s in {".", ".."} for s in segments):
        raise ReadOnlyError("ambiguous request path")
    return "/" + "/".join(s for s in segments if s)


def parameters(url: str, body: Any = None) -> dict[str, list[str]]:
    """Decode form and query parameters without losing duplicate keys."""
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="strict")
    if isinstance(body, str):
        pairs.extend(parse_qsl(body, keep_blank_values=True))
    elif body:
        raise ReadOnlyError("unclassified request body")
    result: dict[str, list[str]] = {}
    for key, value in pairs:
        result.setdefault(key, []).append(value)
    return result


def endpoint(path: str) -> str:
    """Remove the Splunk namespace prefix."""
    parts = path.strip("/").split("/")
    if parts[0] == "services":
        return "/".join(parts[1:])
    if parts[0] == "servicesNS" and len(parts) >= 4:
        return "/".join(parts[3:])
    return path.strip("/")


def check_request(
    method: str,
    url: str,
    configured_origin: str,
    *,
    kind: str = "siem",
    body: Any = None,
    parser: Callable[[str], Any] | None = None,
) -> None:
    """Refuse requests outside the invocation's explicit exceptions."""
    if origin(url) != origin(configured_origin) or urlsplit(url).username is not None:
        raise ReadOnlyError("request leaves the configured origin")
    if not readonly():
        return
    method = method.upper()
    path = canonical_path(url)
    route = endpoint(path)
    if "logout" in path.lower().split("/"):
        raise ReadOnlyError("logout is refused")
    if kind == "soar":
        if method == "GET":
            return
        raise ReadOnlyError(f"{method} is refused for SOAR")
    if method in {"GET", "HEAD"}:
        if route in {"search/parser", "search/v2/parser"}:
            params = parameters(url, body)
            if params.get("parse_only") != ["true"] or params.get("reload_macros") != [
                "false"
            ]:
                raise ReadOnlyError(
                    "search/parser requires parse_only=true and reload_macros=false"
                )
        if route.endswith("/_reload"):
            raise ReadOnlyError("GET reload is refused")
        if path.lower().startswith("/debug/refresh"):
            raise ReadOnlyError("GET refresh is refused")
        # These routes dispatch searches even when called with GET.
        if re.fullmatch(r"(?:search/)?(?:v2/)?jobs/export", route):
            raise ReadOnlyError("GET search dispatch is refused")
        return
    if (
        method == "POST"
        and kind == "web"
        and re.fullmatch(r"[^/]+/account/login", route)
    ):
        return
    if kind == "siem" and method == "POST" and route == "auth/login":
        return
    params = parameters(url, body)
    if (
        kind == "siem"
        and method == "POST"
        and route
        in {
            "search/jobs",
            "search/jobs/export",
            "search/v2/jobs",
            "search/v2/jobs/export",
        }
    ):
        from splunkctl.spl_safety import check_readonly_spl

        if len(params.get("search", [])) != 1:
            raise ReadOnlyError("search dispatch requires exactly one search")
        # Prevent search-job metadata mutations alongside the search.
        allowed = {
            "search",
            "exec_mode",
            "output_mode",
            "count",
            "earliest_time",
            "latest_time",
        }
        if set(params) - allowed:
            raise ReadOnlyError("unclassified search dispatch parameter")
        check_readonly_spl(params["search"][0], parser=parser)
        return
    match = re.fullmatch(r"search/(?:v2/)?jobs/([^/]+)(/control)?", route)
    ctx = current()
    if match and ctx and match[1] in ctx.owned_sids:
        if method == "DELETE" and not match[2] and not params:
            return
        if (
            method == "POST"
            and match[2]
            and set(params) <= {"action", "output_mode"}
            and params.get("action") in [["cancel"], ["finalize"]]
        ):
            return
    raise ReadOnlyError(f"{method} {route} is refused")
