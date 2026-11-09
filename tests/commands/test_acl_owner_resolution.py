"""Data-model namespace precedence and missing-object errors."""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from click.testing import CliRunner
from splunklib.client import Service

from splunkctl.main import cli

from .test_acl import fixture


def invoke_datamodel(operation, configured_owner, found):
    paths = []

    def network(url, message, **kwargs):
        path = urlsplit(url).path
        paths.append(path)
        status = 200
        if path == "/services/authentication/current-context":
            body = {"entry": [{"content": {"username": "admin"}}]}
        elif found and path == f"/servicesNS/{found}/search/datamodel/model/x":
            body = fixture("acl-datamodel")
        else:
            status = 404
            body = {"messages": [{"type": "ERROR", "text": "Object not found"}]}
        return {
            "status": status,
            "reason": "OK" if status == 200 else "Not Found",
            "headers": [],
            "body": io.BytesIO(json.dumps(body).encode()),
        }

    svc = Service(
        host="example.test",
        token="test",  # noqa: S106
        owner=configured_owner,
        handler=network,
    )
    with patch(
        "splunkctl.commands.acl.get_client", return_value=SimpleNamespace(service=svc)
    ):
        result = CliRunner().invoke(
            cli, ["--json", "acl", operation, "data-model", "x"]
        )
    return result, paths


@pytest.mark.parametrize("operation", ["get", "set"])
@pytest.mark.parametrize("found", ["alice", "admin", "nobody"])
def test_datamodel_configured_owner_precedes_authenticated_user(operation, found):
    result, paths = invoke_datamodel(operation, "alice", found)
    assert result.exit_code == 0, result.output
    expected = ["/servicesNS/alice/search/datamodel/model/x"]
    if found != "alice":
        expected += [
            "/services/authentication/current-context",
            "/servicesNS/admin/search/datamodel/model/x",
        ]
    if found == "nobody":
        expected.append("/servicesNS/nobody/search/datamodel/model/x")
    assert paths == expected


@pytest.mark.parametrize("operation", ["get", "set"])
@pytest.mark.parametrize("configured_owner", ["alice", None, "-"])
def test_datamodel_all_candidates_404_returns_not_found_hint(
    operation, configured_owner
):
    result, paths = invoke_datamodel(operation, configured_owner, None)
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["kind"] == "not_found"
    assert "pass --current-owner" in result.stderr
    expected = []
    if configured_owner == "alice":
        expected.append("/servicesNS/alice/search/datamodel/model/x")
    expected += [
        "/services/authentication/current-context",
        "/servicesNS/admin/search/datamodel/model/x",
        "/servicesNS/nobody/search/datamodel/model/x",
    ]
    assert paths == expected
