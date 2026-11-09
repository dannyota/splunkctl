"""Policy and invocation headers at the final SDK and Requests boundary."""

import io
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree

import requests

from splunkctl.request_context import current, readonly, user_agent
from splunkctl.request_policy import (
    ReadOnlyError,
    canonical_path,
    check_request,
    endpoint,
    origin,
)


def _remember_sid(url: str, body: bytes) -> None:
    ctx = current()
    if ctx is None or endpoint(canonical_path(url)) not in {
        "search/jobs",
        "search/v2/jobs",
    }:
        return
    try:
        data = json.loads(body)
        sid = data.get("sid")
    except (ValueError, AttributeError):
        try:
            sid = ElementTree.fromstring(body).findtext("sid")  # noqa: S314
        except ElementTree.ParseError:
            return
    if isinstance(sid, str) and sid:
        ctx.owned_sids.add(sid)


class PolicySession(requests.Session):
    """Check every prepared request, including each redirect hop."""

    def __init__(self, configured_origin: str, *, kind: str = "siem") -> None:
        """Bind requests to the configured server and product policy."""
        super().__init__()
        self.configured_origin = configured_origin
        self.kind = kind

    def send(
        self, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        """Enforce method/origin policy and replace competing User-Agents."""
        request.headers["User-Agent"] = user_agent()
        url = request.url or ""

        def parser(spl: str) -> Any:
            parsed = urlsplit(url)
            prefix = parsed.path.split("/search/", 1)[0]
            target = f"{parsed.scheme}://{parsed.netloc}{prefix}/search/parser"
            response = self.get(
                target,
                params={
                    "q": spl,
                    "output_mode": "json",
                    "parse_only": "true",
                    "reload_macros": "false",
                },
                headers={
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() in {"authorization", "cookie"}
                },
                timeout=kwargs.get("timeout"),
                verify=kwargs.get("verify", True),
            )
            response.raise_for_status()
            return response.json()

        check_request(
            request.method or "GET",
            url,
            self.configured_origin,
            kind=self.kind,
            body=request.body,
            parser=parser,
        )
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location")
            if location:
                from urllib.parse import urljoin

                if origin(urljoin(url, location)) != origin(self.configured_origin):
                    raise ReadOnlyError("redirect leaves the configured origin")
        if request.method == "POST" and response.ok and readonly():
            # Only search creation needs response buffering; exports remain streaming.
            if endpoint(canonical_path(url)) in {"search/jobs", "search/v2/jobs"}:
                _remember_sid(url, response.content)
        return response


def sdk_handler(
    handler: Callable[..., Any], configured_origin: str
) -> Callable[..., Any]:
    """Wrap either supported SDK version's handler protocol."""

    def dispatch(url: str, message: dict[str, Any], **kwargs: Any) -> Any:
        message = dict(message)
        message["headers"] = [
            (k, v) for k, v in message.get("headers", []) if k.lower() != "user-agent"
        ] + [("User-Agent", user_agent())]

        def parser(spl: str) -> Any:
            parsed = urlsplit(url)
            prefix = parsed.path.split("/search/", 1)[0]
            target = f"{parsed.scheme}://{parsed.netloc}{prefix}/search/parser?"
            target += urlencode(
                {
                    "q": spl,
                    "output_mode": "json",
                    "parse_only": "true",
                    "reload_macros": "false",
                }
            )
            response = dispatch(
                target, {"method": "GET", "headers": message["headers"]}, **kwargs
            )
            if int(response["status"]) >= 300:
                raise ReadOnlyError("search/parser request failed")
            return json.loads(response["body"].read())

        method = message.get("method", "GET").upper()
        check_request(
            method, url, configured_origin, body=message.get("body"), parser=parser
        )
        response = handler(url, message, **kwargs)
        if 300 <= int(response["status"]) < 400:
            from urllib.parse import urljoin

            for key, value in response.get("headers", []):
                if key.lower() == "location" and origin(urljoin(url, value)) != origin(
                    configured_origin
                ):
                    raise ReadOnlyError("redirect leaves the configured origin")
        if readonly() and method == "POST" and int(response["status"]) < 300:
            if endpoint(canonical_path(url)) in {"search/jobs", "search/v2/jobs"}:
                stream = response["body"]
                body = stream.read()
                if isinstance(body, str):
                    body = body.encode()
                response = dict(response, body=io.BytesIO(body))
                _remember_sid(url, body)
        return response

    return dispatch
