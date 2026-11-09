"""Raw API post-processing must stop before the real SDK transport."""

import io
import json
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner
from splunklib.client import Service

from splunkctl.commands.api import _request
from splunkctl.main import cli
from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError
from splunkctl.transport import sdk_handler


@pytest.fixture
def sdk():
    seen = []

    def network(url, message, **kwargs):
        seen.append(str(url))
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    service = Service(
        host="example.test",
        token="test",  # noqa: S106
        handler=sdk_handler(network, "https://example.test:8089"),
    )
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = service
        yield seen


@pytest.mark.parametrize(
    "prefix",
    [
        "search/jobs",
        "search/v2/jobs",
        "/servicesNS/nobody/search/search/jobs",
        "/servicesNS/nobody/search/search/v2/jobs",
    ],
)
@pytest.mark.parametrize(
    "route",
    ["results", "results_preview", "events", "summary", "timeline", "future/subroute"],
)
def test_cli_sdk_refuses_postprocessing(sdk, prefix, route):
    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "--read-only",
            "api",
            "get",
            f"{prefix}/x/{route}",
            "--param",
            "search=| outputlookup a.csv",
        ],
    )
    assert result.exit_code == 1, result.output
    assert json.loads(result.stderr)["error"]["kind"] == "permission"
    assert not sdk


@pytest.mark.parametrize("version", ["", "v2/"])
def test_sdk_head_refuses_postprocessing(sdk, version):
    # HEAD has no CLI leaf; exercise the same API request adapter and SDK.
    with invocation("api", True), pytest.raises(ReadOnlyError):
        _request(
            click.Context(click.Command("api")),
            "HEAD",
            f"/servicesNS/nobody/search/search/{version}jobs/x/results",
            [("search", "| outputlookup a.csv")],
        )
    assert not sdk


@pytest.mark.parametrize(
    "value", ["false", "true", "", "0", "false&check_risky_command=true"]
)
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
def test_sdk_refuses_risky_check_parameter(sdk, method, value):
    with (
        invocation("api", True),
        pytest.raises(ReadOnlyError, match="check_risky_command"),
    ):
        _request(
            click.Context(click.Command("api")),
            method,
            "/services/search/jobs/x/results",
            [("check_risky_command", value)],
        )
    assert not sdk
