"""Form selection through real SDK requests with lab-shaped responses."""

import io
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from click.testing import CliRunner
from splunklib.client import Service

from splunkctl.main import cli
from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError
from splunkctl.transport import sdk_handler


def response(status=200, body=b'{"results":[]}'):
    return {"status": status, "reason": "test", "headers": [], "body": io.BytesIO(body)}


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("command", ["run", "oneshot", "export"])
@pytest.mark.parametrize("failure", [405, "connection", 400])
def test_macro_parser_failure_mode(readonly, command, failure):
    dispatched = []
    parsed = []
    detail = (
        "Unknown search command 'broken'." if failure == 400 else "Method unavailable"
    )

    def network(url, message, **kwargs):
        if urlsplit(str(url)).path.endswith("/parser"):
            parsed.append(str(url))
            if failure == "connection":
                raise ConnectionError("parser unavailable")
            return response(
                failure, json.dumps({"messages": [{"text": detail}]}).encode()
            )
        dispatched.append(
            parse_qs(
                message["body"].decode()
                if isinstance(message["body"], bytes)
                else message["body"]
            )["search"][0]
        )
        return response(
            body=b"<response><sid>mine</sid></response>"
            if command == "run"
            else b'{"results":[]}'
        )

    svc = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    svc._splunk_version = (10, 6, 1)
    svc._instance_type = "enterprise"
    with patch("splunkctl.commands.search.get_client") as client:
        client.return_value.service = svc
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                *(["--read-only"] if readonly else []),
                "search",
                command,
                *(["--detach"] if command == "run" else []),
                "`macro`",
            ],
        )
    assert len(parsed) == 1
    assert result.exit_code == int(readonly), result.output
    assert dispatched == ([] if readonly else ["search `macro`"])
    if readonly and failure != "connection":
        assert detail in result.stderr


@pytest.mark.parametrize("source", ["body", "url"])
@pytest.mark.parametrize("accepted", [False, True])
def test_readonly_classifies_exact_dispatched_spl(source, accepted):
    classified = []
    dispatched = []
    spl = "search ```comment``` `gen`  "

    def network(url, message, **kwargs):
        if urlsplit(str(url)).path.endswith("/parser"):
            classified.append(
                parse_qs(
                    message["body"].decode()
                    if isinstance(message["body"], bytes)
                    else message["body"]
                )["q"][0]
            )
            if not accepted:
                return response(
                    400, b'{"messages":[{"text":"must be the first command"}]}'
                )
            return response(body=b'{"commands":[{"command":"search"}]}')
        params = parse_qs(urlsplit(str(url)).query) | parse_qs(
            message.get("body", b"").decode()
            if isinstance(message.get("body", ""), bytes)
            else message.get("body", "")
        )
        dispatched.append(params["search"][0])
        return response(body=b"<response><sid>mine</sid></response>")

    svc = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    with invocation("api post", True):

        def dispatch():
            if source == "url":
                svc.http.post(
                    "https://example.test:8089/services/search/jobs?"
                    + urlencode({"search": spl})
                )
            else:
                svc.post("search/jobs", search=spl)

        if accepted:
            dispatch()
        else:
            with pytest.raises(ReadOnlyError, match="must be the first command"):
                dispatch()
    assert classified == [spl]
    assert dispatched == ([spl] if accepted else [])


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("api_version", [1, 2])
@pytest.mark.parametrize("spl", ["`gen`", "  ```first``` \n ```second``` `gen`  "])
def test_generating_macro_selected_before_job_creation(readonly, api_version, spl):
    jobs = []
    results = []
    parsed = []
    detail = (
        "Error in 'makeresults' command: "
        "This command must be the first command of a search."
    )

    def network(url, message, **kwargs):
        path = urlsplit(str(url)).path
        body = message.get("body", "")
        params = parse_qs(body.decode() if isinstance(body, bytes) else body)
        if path.endswith("/parser"):
            assert message["method"] == "POST"
            assert params["parse_only"] == ["true"]
            assert params["reload_macros"] == ["false"]
            assert params["output_mode"] == ["json"]
            parsed.append(params["q"][0])
            if params["q"][0].startswith("search "):
                return response(
                    400, json.dumps({"messages": [{"text": detail}]}).encode()
                )
            return response(body=b'{"commands":[{"command":"makeresults"}]}')
        if path.rstrip("/").endswith("/jobs"):
            assert message["method"] == "POST"
            # Splunk accepts even the wrong form and creates a failed job.
            jobs.append(params["search"][0])
            return response(body=b"<response><sid>mine</sid></response>")
        if path.endswith("/results"):
            results.append(path)
            if jobs[0].startswith("search "):
                return response(
                    400, json.dumps({"messages": [{"text": detail}]}).encode()
                )
            return response(body=b'{"results":[{"count":"1"}]}')
        assert path.endswith("/jobs/mine")
        state = "FAILED" if jobs[0].startswith("search ") else "DONE"
        return response(
            body=(
                '<entry xmlns:s="http://dev.splunk.com/ns/rest"><content><s:dict>'
                '<s:key name="eai:acl"><s:dict><s:key name="owner">nobody</s:key>'
                '<s:key name="app">search</s:key><s:key name="sharing">app</s:key>'
                '</s:dict></s:key><s:key name="isDone">1</s:key>'
                f'<s:key name="dispatchState">{state}</s:key>'
                '<s:key name="resultCount">1</s:key></s:dict></content></entry>'
            ).encode()
        )

    svc = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    svc._splunk_version = (8, 2, 0) if api_version == 1 else (10, 6, 1)
    svc._instance_type = "enterprise"
    with patch("splunkctl.commands.search.get_client") as client:
        client.return_value.service = svc
        result = CliRunner().invoke(
            cli,
            ["--json", *(["--read-only"] if readonly else []), "search", "run", spl],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"count": "1"}]
    assert jobs == [spl.strip()]
    assert parsed == [
        "search " + spl.strip(),
        spl.strip(),
        *([spl.strip()] if readonly else []),
    ]
    assert results == [
        "/servicesNS/nobody/search/search/"
        f"{'v2/' if api_version == 2 else ''}jobs/mine/results"
    ]
