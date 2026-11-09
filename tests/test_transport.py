import io
import json
from unittest.mock import Mock

import pytest
import requests

from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError
from splunkctl.transport import PolicySession, sdk_handler


def test_sdk_replaces_all_competing_headers_and_tracks_sid():
    underlying = Mock(
        return_value={
            "status": 201,
            "headers": [],
            "body": io.BytesIO(b"<response><sid>mine</sid></response>"),
        }
    )
    handler = sdk_handler(underlying, "https://example.test")
    with invocation("search run", True) as ctx:
        response = handler(
            "https://example.test/services/search/jobs",
            {
                "method": "POST",
                "headers": [("user-agent", "bad"), ("User-Agent", "bad")],
                "body": "search=%7C+makeresults&exec_mode=normal",
            },
        )
        assert ctx.owned_sids == {"mine"}
        assert response["body"].read() == b"<response><sid>mine</sid></response>"
        headers = underlying.call_args.args[1]["headers"]
        assert len([k for k, v in headers if k.lower() == "user-agent"]) == 1
        assert ctx.request_id in headers[-1][1]


def test_sdk_decoded_spl_checked_before_dispatch():
    underlying = Mock()
    handler = sdk_handler(underlying, "https://example.test")
    with invocation("api post", True), pytest.raises(ReadOnlyError, match="delete"):
        handler(
            "https://example.test/services/search/jobs",
            {
                "method": "POST",
                "headers": [],
                "body": "search=search+index%3Dmain+%7C+delete",
            },
        )
    underlying.assert_not_called()


def test_sdk_parser_post_shape_and_safe_flags():
    underlying = Mock(
        return_value={
            "status": 200,
            "headers": [],
            "body": io.BytesIO(
                json.dumps({"commands": [{"command": "makeresults"}]}).encode()
            ),
        }
    )
    handler = sdk_handler(underlying, "https://example.test")
    with invocation("search export", True):
        handler(
            "https://example.test/services/search/jobs/export",
            {"method": "POST", "headers": [], "body": "search=%7C+%60macro%60"},
        )
    parser_url, parser_message = underlying.call_args_list[0].args
    assert parser_url.endswith("/search/parser")
    assert "parse_only=true" in parser_message["body"]
    assert "reload_macros=false" in parser_message["body"]
    assert parser_message["method"] == "POST"
    assert (
        dict(parser_message["headers"])["Content-Type"]
        == "application/x-www-form-urlencoded"
    )


@pytest.mark.parametrize("readonly", [False, True])
def test_sdk_unfollowed_redirect_allowed(readonly):
    handler = sdk_handler(
        Mock(
            return_value={
                "status": 302,
                "headers": [("Location", "https://evil.test/")],
            }
        ),
        "https://example.test",
    )
    with invocation("info", readonly):
        response = handler(
            "https://example.test/services/server/info",
            {"method": "GET", "headers": []},
        )
    assert response["status"] == 302


def test_requests_checks_prepared_redirect_hop():
    session = PolicySession("https://example.test")
    request = requests.Request("GET", "https://evil.test/").prepare()
    with invocation("info", True), pytest.raises(ReadOnlyError, match="origin"):
        session.send(request)


def test_requests_refuses_logout_before_adapter_dispatch():
    session = PolicySession("https://example.test", kind="web")
    adapter = Mock()
    session.mount("https://", adapter)
    with invocation("info", True), pytest.raises(ReadOnlyError, match="logout"):
        session.get("https://example.test/en-US/account/logout")
    adapter.send.assert_not_called()


def test_requests_redirect_chain_never_dispatches_off_origin():
    class RedirectAdapter(requests.adapters.BaseAdapter):
        def __init__(self):
            self.urls = []

        def send(self, request, **kwargs):
            self.urls.append(request.url)
            response = requests.Response()
            response.status_code = 302
            response.headers["Location"] = "https://evil.test/"
            response._content = b""
            response.request = request
            response.url = request.url
            return response

        def close(self):
            pass

    session = PolicySession("https://example.test")
    adapter = RedirectAdapter()
    session.mount("https://", adapter)
    with invocation("info", True), pytest.raises(ReadOnlyError, match="origin"):
        session.get("https://example.test/services/server/info")
    assert adapter.urls == ["https://example.test/services/server/info"]


@pytest.mark.parametrize("namespace", ["services", "servicesNS/nobody/search"])
def test_requests_parser_posts_safe_form(namespace):
    class ParserAdapter(requests.adapters.BaseAdapter):
        def __init__(self):
            self.calls = []

        def send(self, request, **kwargs):
            from urllib.parse import parse_qs

            self.calls.append(request)
            response = requests.Response()
            response.status_code = 200
            response.request = request
            response.url = request.url
            if request.url.endswith("/parser"):
                assert request.method == "POST"
                assert parse_qs(request.body) == {
                    "q": ["`safe`"],
                    "output_mode": ["json"],
                    "parse_only": ["true"],
                    "reload_macros": ["false"],
                }
                response._content = b'{"commands":[{"command":"makeresults"}]}'
            else:
                response._content = b'{"sid":"mine"}'
            return response

        def close(self):
            pass

    session = PolicySession("https://example.test")
    adapter = ParserAdapter()
    session.mount("https://", adapter)
    with invocation("search run", True) as ctx:
        session.post(
            f"https://example.test/{namespace}/search/jobs", data={"search": "`safe`"}
        )
        assert ctx.owned_sids == {"mine"}
    assert len(adapter.calls) == 2


def test_sdk_binary_upload_body_unchanged():
    """Search retry inspection must leave unrelated binary requests alone."""
    from splunklib.client import Service

    bodies = []

    def network(url, message, **kwargs):
        bodies.append(message["body"])
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    service.post("receivers/simple", body=b"\xff\x00")
    assert bodies == [b"\xff\x00"]
