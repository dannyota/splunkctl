"""Regressions for lab-verified Splunk and SDK request shapes."""

import io
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner
from splunklib.client import Service

from splunkctl.main import cli
from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError, check_request
from splunkctl.transport import sdk_handler


@pytest.mark.parametrize("method", ["GET", "POST", "HEAD"])
@pytest.mark.parametrize("prefix", ["/services/", "/servicesNS/nobody/search/"])
@pytest.mark.parametrize("version", ["", "v1/", "v2/"])
@pytest.mark.parametrize("owned", [False, True])
@pytest.mark.parametrize("param", ["search=", "check_risky_command=false", "unknown=x"])
def test_result_policy(method, prefix, version, owned, param):
    with invocation("test", True) as ctx:
        if owned:
            ctx.owned_sids.add("mine")
        with pytest.raises(ReadOnlyError):
            check_request(
                method,
                f"https://example.test{prefix}search/{version}jobs/mine/results?{param}",
                "https://example.test",
            )


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("route", ["results", "results_preview", "events"])
@pytest.mark.parametrize("version", ["", "v1/", "v2/"])
@pytest.mark.parametrize("owned", [False, True])
def test_result_read_ownership(method, route, version, owned):
    with invocation("test", True) as ctx:
        if owned:
            ctx.owned_sids.add("mine")

        def call():
            check_request(
                method,
                f"https://example.test/servicesNS/nobody/search/search/{version}jobs/mine/{route}?count=5&offset=1&f=a&f=b&output_mode=json",
                "https://example.test",
            )

        if owned:
            call()
        else:
            with pytest.raises(ReadOnlyError):
                call()


@pytest.mark.parametrize(
    "accessor,route",
    [("results", "results"), ("preview", "results_preview"), ("events", "events")],
)
@pytest.mark.parametrize("api_version", [1, 2])
def test_real_sdk_job_reads(accessor, route, api_version):
    seen = []

    def network(url, message, **kwargs):
        seen.append((str(url), message))
        return {
            "status": 200,
            "reason": "OK",
            "headers": [],
            "body": io.BytesIO(
                b"<response><sid>mine</sid></response>"
                if urlsplit(str(url)).path.rstrip("/").endswith("/jobs")
                else b'{"results":[]}'
            ),
        }

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    service._splunk_version = (8, 2, 0) if api_version == 1 else (10, 6, 1)
    service._instance_type = "enterprise"
    with invocation("search run", True) as ctx:
        job = service.jobs.create("| makeresults")
        assert ctx.owned_sids == {"mine"}
        assert getattr(job, accessor)(count=5, offset=1, output_mode="json").read()
    url, message = seen[-1]
    assert (
        urlsplit(url).path
        == f"/services/search/{'v2/' if api_version == 2 else ''}jobs/mine/{route}"
    )
    assert message["method"] == ("POST" if api_version == 2 else "GET")


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("command", ["oneshot", "export", "run"])
@pytest.mark.parametrize(
    "spl,winning,generating",
    [
        ("`outer`", "search `outer`", False),
        ("`gen`", "`gen`", True),
        (
            "  ```note``` error | stats count",
            "search ```note``` error | stats count",
            False,
        ),
        ("```note``` | makeresults", "```note``` | makeresults", False),
        ("```one```  ```two``` `gen`", "```one```  ```two``` `gen`", True),
    ],
)
def test_cli_macro_and_comment_normalization(
    readonly, command, spl, winning, generating
):
    seen = []

    def network(url, message, **kwargs):
        body = message.get("body", "")
        params = parse_qs(body.decode() if isinstance(body, bytes) else body)
        parser = str(url).endswith("/parser")
        query = params["q" if parser else "search"][0]
        seen.append((parser, query))
        if generating and query.startswith("search "):
            body = (
                b'<response><messages><msg type="ERROR">'
                b"Error in 'makeresults' command: This command must be the first "
                b"command of a search.</msg></messages></response>"
            )
            return {
                "status": 400,
                "reason": "Bad Request",
                "headers": [],
                "body": io.BytesIO(body),
            }
        assert query == winning
        body = (
            json.dumps(
                {
                    "commands": [
                        {"command": c}
                        for c in (
                            ["makeresults"]
                            if generating
                            else ["search", "head", "stats"]
                        )
                    ]
                }
            ).encode()
            if parser
            else b"<response><sid>mine</sid></response>"
            if command == "run"
            else b'{"result":{"count":"1"}}\n'
        )
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(body)}

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    service._splunk_version = (10, 6, 1)
    service._instance_type = "enterprise"
    with patch("splunkctl.commands.search.get_client") as client:
        client.return_value.service = service
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                *(["--read-only"] if readonly else []),
                "search",
                command,
                *(["--detach"] if command == "run" else []),
                spl,
            ],
        )
    assert result.exit_code == 0, result.output
    assert seen[-1] == (False, winning)
    assert len([x for x in seen if not x[0]]) == (
        2 if generating and not readonly else 1
    )
    assert len([x for x in seen if x[0]]) == (
        (2 if generating else 1)
        if readonly and ("`gen`" in spl or "`outer`" in spl)
        else 0
    )


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("spl", ["`outer`", "search `outer`", "error", "| makeresults"])
@pytest.mark.parametrize(
    "status,message",
    [
        (400, "Unknown search command 'index'."),
        (403, "must be the first command"),
        (400, "must be the first command"),
    ],
)
def test_search_error_retry_scope(readonly, spl, status, message):
    seen = []

    def network(url, request, **kwargs):
        seen.append(str(url))
        body = (
            '<response><messages><msg type="ERROR">'
            + message
            + "</msg></messages></response>"
        ).encode()
        return {
            "status": status,
            "reason": "Bad Request",
            "headers": [],
            "body": io.BytesIO(body),
        }

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    service._splunk_version = (10, 6, 1)
    service._instance_type = "enterprise"
    with patch("splunkctl.commands.search.get_client") as client:
        client.return_value.service = service
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                *(["--read-only"] if readonly else []),
                "search",
                "oneshot",
                spl,
            ],
        )
    assert result.exit_code == 1
    assert len(seen) == (
        2
        if spl == "`outer`" and status == 400 and message == "must be the first command"
        else 1
    )
    if readonly and spl == "`outer`":
        error = json.loads(result.stderr.splitlines()[-1])
        assert error["error"]["kind"] == "permission"
        assert (
            "read-only: search/parser rejected the search: " + message in result.stderr
        )


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("version", ["", "v1/", "v2/"])
@pytest.mark.parametrize(
    "extra", ["", "&unknown=x", "&parse_only=false", "&reload_macros=true"]
)
def test_parser_parameter_policy(method, version, extra):
    with invocation("test", True):

        def call():
            check_request(
                method,
                f"https://example.test/servicesNS/nobody/search/search/{version}parser?parse_only=true&reload_macros=false&q=x&output_mode=json{extra}",
                "https://example.test",
            )

        if extra:
            with pytest.raises(ReadOnlyError):
                call()
        else:
            call()


def test_rest_guidance():
    from splunkctl.spl_safety import check_readonly_spl

    with pytest.raises(ReadOnlyError) as error:
        check_readonly_spl("| rest /services/server/info")
    assert (
        str(error.value)
        == "read-only: SPL command rest is refused; use `splunkctl api get` instead"
    )


@pytest.mark.parametrize("encoding", ["xml", "json"])
def test_parser_error_message_truncated(encoding):
    detail = "Unknown search command: " + "x" * 250

    def network(url, request, **kwargs):
        body = (
            json.dumps({"messages": [{"type": "ERROR", "text": detail}]}).encode()
            if encoding == "json"
            else (
                '<response><messages><msg type="ERROR">'
                + detail
                + "</msg></messages></response>"
            ).encode()
        )
        return {
            "status": 400,
            "reason": "Bad Request",
            "headers": [],
            "body": io.BytesIO(body),
        }

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )  # noqa: S106
    service._splunk_version = (10, 6, 1)
    service._instance_type = "enterprise"
    with invocation("test", True), pytest.raises(ReadOnlyError) as error:
        service.jobs.oneshot("search `outer`", output_mode="json")
    assert (
        str(error.value)
        == "read-only: search/parser rejected the search: " + detail[:200]
    )
