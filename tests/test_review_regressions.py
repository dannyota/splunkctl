"""Exercise policy at real SDK and Requests dispatch boundaries."""

import io
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import click
import pytest
import requests
from splunklib.client import Service

from splunkctl.auth import detector
from splunkctl.auth.adapters import SIEMAdapter
from splunkctl.client import SplunkClient
from splunkctl.commands.api import _request
from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError
from splunkctl.transport import PolicySession, sdk_handler


class Adapter(requests.adapters.BaseAdapter):
    def __init__(self):
        self.urls = []

    def send(self, request, **kwargs):
        self.urls.append(request.url)
        response = requests.Response()
        response.status_code = 302 if len(self.urls) == 1 else 200
        response.headers["Location"] = "https://idp.test/realm/protocol/saml"
        response._content = b"{}"
        response.request = request
        response.url = request.url
        return response

    def close(self):
        pass


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("probe", [detector.probe, detector.siem_idp_issuer])
def test_detector_external_idp_redirect(readonly, probe, monkeypatch):
    adapter = Adapter()
    monkeypatch.setattr(
        requests.Session, "get_adapter", lambda *args, **kwargs: adapter
    )
    with invocation("auth", readonly):
        result = probe("https://example.test", verify=True, timeout=1)
    assert result == (
        "browser" if probe is detector.probe else "https://idp.test/realm"
    )
    assert len(adapter.urls) == 1


def test_saml_logout_redirect_normal_mode(monkeypatch):
    adapter = Adapter()
    monkeypatch.setattr(
        requests.Session, "get_adapter", lambda *args, **kwargs: adapter
    )
    with invocation("auth logout", False):
        SIEMAdapter().logout(
            {"cookie": "session", "session_key": "test"},
            web_url="https://example.test",
            verify=True,
            timeout=1,
        )
    assert adapter.urls == [
        "https://example.test/en-US/account/logout",
        "https://idp.test/realm/protocol/saml",
    ]


def test_followed_redirect_refused_at_hop():
    adapter = Adapter()
    session = PolicySession("https://example.test")
    session.mount("https://", adapter)
    with invocation("info", True), pytest.raises(ReadOnlyError, match="request leaves"):
        session.get("https://example.test/services/server/info")
    assert adapter.urls == ["https://example.test/services/server/info"]


@pytest.mark.parametrize("method", ["oneshot", "export", "create"])
def test_real_sdk_search_serialization(method):
    seen = []

    def low_level(url, message, **kwargs):
        seen.append((str(url), message))
        return {
            "status": 200,
            "reason": "OK",
            "headers": [],
            "body": io.BytesIO(b"<response><sid>mine</sid></response>"),
        }

    svc = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    svc._splunk_version = (10, 0, 0)
    svc._instance_type = "enterprise"
    params = dict(
        output_mode="xml",
        earliest_time="-1h",
        latest_time="now",
        count=10,
        max_count=100,
        rf="host",
        adhoc_search_level="fast",
        time_format="%s",
    )
    if method == "create":
        params["exec_mode"] = "normal"
    with invocation("search", True):
        getattr(svc.jobs, method)("| makeresults", **params)
    assert len(seen) == 1
    url, message = seen[0]
    assert urlsplit(url).path == (
        "/services/search/v2/jobs/export"
        if method == "export"
        else "/services/search/v2/jobs/"
    )
    assert message["method"] == "POST"
    expected = {
        "search": ["| makeresults"],
        "output_mode": ["xml"],
        "earliest_time": ["-1h"],
        "latest_time": ["now"],
        "count": ["10"],
        "max_count": ["100"],
        "rf": ["host"],
        "adhoc_search_level": ["fast"],
        "time_format": ["%s"],
    }
    if method != "create":
        expected["segmentation"] = ["none"]
    if method != "export":
        expected["exec_mode"] = ["normal" if method == "create" else "oneshot"]
    assert parse_qs(message["body"].decode()) == expected


@pytest.mark.parametrize(
    "prefix",
    [
        "/services",
        "/servicesNS/admin/search",
        "/servicesNS/search/app",
        "/servicesNS/search/search",
    ],
)
@pytest.mark.parametrize("transport", ["sdk", "requests"])
def test_parser_preserves_namespace(prefix, transport):
    seen = []

    def low_level(url, message, **kwargs):
        seen.append(str(url))
        return {
            "status": 200,
            "reason": "OK",
            "headers": [],
            "body": io.BytesIO(b'{"commands":[{"command":"makeresults"}]}'),
        }

    url = "https://example.test" + prefix + "/search/jobs/export"
    with invocation("search", True):
        if transport == "sdk":
            sdk_handler(low_level, "https://example.test")(
                url, {"method": "POST", "body": "search=%7C+%60macro%60"}
            )
        else:

            class ParserAdapter(Adapter):
                def send(self, request, **kwargs):
                    seen.append(request.url)
                    response = super().send(request, **kwargs)
                    response.status_code = 200
                    response._content = b'{"commands":[{"command":"makeresults"}]}'
                    return response

            session = PolicySession("https://example.test")
            session.mount("https://", ParserAdapter())
            session.post(url, data={"search": "| `macro`"})
    assert urlsplit(seen[0]).path == prefix + "/search/parser"


@pytest.mark.parametrize(
    "body,content_type",
    [
        ('{"name":"日本語 café"}', "application/json"),
        ("name=日本語 café", "application/x-www-form-urlencoded"),
    ],
)
def test_api_unicode_body_bytes(body, content_type):
    seen = []

    def low_level(url, message, **kwargs):
        seen.append((str(url), message))
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = service
        with invocation("api post", False):
            _request(
                click.Context(click.Command("api")),
                "POST",
                "/services/test",
                [("f", "a"), ("f", "b")],
                body=body,
                content_type=content_type,
            )
    assert seen[0][1]["body"] == body.encode("utf-8")
    assert parse_qs(urlsplit(seen[0][0]).query) == {
        "f": ["a", "b"],
        "output_mode": ["json"],
    }
    assert ("Content-Type", content_type) in seen[0][1]["headers"]


@pytest.mark.parametrize(
    "host,authority", [("::1", "[::1]:8089"), ("example.test", "example.test:8089")]
)
def test_client_policy_origin(host, authority):
    def low_level(url, message, **kwargs):
        assert urlsplit(url).netloc == authority
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    with (
        patch("splunkctl.client.handler", return_value=low_level),
        invocation("info", True),
    ):
        client = SplunkClient(host=host, token="test")  # noqa: S106
        client.service.get("/services/server/info")


@pytest.mark.parametrize(
    "parameter",
    [
        "action.email",
        "actions",
        "alert_actions",
        "trigger_actions",
        "custom",
        "status_buckets",
    ],
)
def test_sdk_unsafe_search_parameters_refused(parameter):
    def low_level(*args, **kwargs):
        pytest.fail("unsafe request reached transport")

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    service._splunk_version = (10, 0, 0)
    service._instance_type = "enterprise"
    with invocation("search", True), pytest.raises(ReadOnlyError, match="parameter"):
        service.jobs.oneshot("| makeresults", **{parameter: "1"})


@pytest.mark.parametrize("method", ["create", "oneshot", "export"])
def test_sdk_search_retention_timeout_refused(method):
    def low_level(*args, **kwargs):
        pytest.fail("retention request reached transport")

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    service._splunk_version = (10, 0, 0)
    service._instance_type = "enterprise"
    with invocation("search", True), pytest.raises(ReadOnlyError, match="parameter"):
        getattr(service.jobs, method)("| makeresults", timeout=315360000)


def test_api_utf8_form_policy_enforced():
    def low_level(*args, **kwargs):
        pytest.fail("write reached transport")

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = service
        with invocation("api post", True), pytest.raises(ReadOnlyError, match="delete"):
            _request(
                click.Context(click.Command("api")),
                "POST",
                "/services/search/jobs",
                [],
                body="search=search index=main | delete",
                content_type="application/x-www-form-urlencoded",
            )


@pytest.mark.parametrize("metric", [None, "cpu"])
def test_metrics_command_real_sdk_dispatch(metric):
    from click.testing import CliRunner

    from splunkctl.commands.search import search_group

    seen = []

    def low_level(url, message, **kwargs):
        seen.append(message)
        return {
            "status": 200,
            "reason": "OK",
            "headers": [],
            "body": io.BytesIO(b'{"results":[]}'),
        }

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    service._splunk_version = (10, 0, 0)
    service._instance_type = "enterprise"
    args = ["metrics", "--index", "metrics"]
    if metric:
        args.extend(["--metric", metric])
    with patch("splunkctl.commands.search.get_client") as client:
        client.return_value.service = service
        with invocation("search metrics", True):
            result = CliRunner().invoke(search_group, args, obj={})
    assert result.exit_code == 0, result.output
    assert parse_qs(seen[0]["body"].decode())["search"] == [
        '| mcatalog values(_dims) WHERE metric_name="cpu" AND index="metrics"'
        if metric
        else '| mcatalog values(metric_name) WHERE index="metrics"'
    ]


def test_api_generated_unicode_form_bytes():
    seen = []

    def low_level(url, message, **kwargs):
        seen.append((str(url), message))
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(low_level, "https://example.test:8089"),
    )
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = service
        with invocation("api post", False):
            _request(
                click.Context(click.Command("api")),
                "POST",
                "/services/test",
                [("name", "日本語 café")],
            )
    assert seen[0][1]["body"] == b"name=%E6%97%A5%E6%9C%AC%E8%AA%9E+caf%C3%A9"
    assert urlsplit(seen[0][0]).query == "output_mode=json"
