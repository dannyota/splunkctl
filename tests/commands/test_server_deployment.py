"""Tests for deployment-server serverclass commands."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server_deployment.get_client"


def _json_resp(data: dict[str, Any]) -> MagicMock:
    """Build a MagicMock response with JSON body."""
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


def _http_error(status: int, body_text: str) -> Exception:
    """Build a splunklib HTTPError with the given status and body."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "Service Unavailable" if status == 503 else "Error"
    resp.body.read.return_value = (
        f"<response><messages><msg>{body_text}</msg></messages></response>".encode()
    )
    resp.headers = {}
    from splunklib.binding import HTTPError

    return HTTPError(resp)


# ---- serverclasses list ----


_SC_ENTRIES = {
    "entry": [
        {
            "name": "linux_forwarders",
            "content": {
                "restartSplunkd": True,
                "stateOnClient": "enabled",
                "whitelist.0": "*.linux.example.com",
                "blacklist.0": "devbox.linux.example.com",
            },
        },
        {
            "name": "windows_forwarders",
            "content": {
                "restartSplunkd": False,
                "stateOnClient": "noop",
            },
        },
    ]
}


@patch(_PATCH)
def test_serverclasses_list(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(_SC_ENTRIES)

    result = CliRunner().invoke(cli, ["--json", "server", "serverclasses", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "linux_forwarders"
    assert data[0]["restartSplunkd"] is True
    assert data[0]["stateOnClient"] == "enabled"
    assert data[0]["whitelist"] == ["*.linux.example.com"]
    assert data[0]["blacklist"] == ["devbox.linux.example.com"]
    assert data[1]["name"] == "windows_forwarders"
    assert data[1]["whitelist"] == []
    assert data[1]["blacklist"] == []


@patch(_PATCH)
def test_serverclasses_list_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "serverclasses", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


@patch(_PATCH)
def test_serverclasses_list_disabled(mock_gc: MagicMock) -> None:
    """503 when deployment server not enabled -> clean disabled, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, "Deployment server is not enabled")

    result = CliRunner().invoke(cli, ["--json", "server", "serverclasses", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "disabled"


@patch(_PATCH)
def test_serverclasses_list_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 propagates to the error classifier."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "serverclasses", "list"])
    assert result.exit_code == 1


# ---- serverclasses get ----


_SC_DETAIL = {
    "entry": [
        {
            "name": "linux_forwarders",
            "content": {
                "restartSplunkd": True,
                "stateOnClient": "enabled",
                "whitelist.0": "*.linux.example.com",
                "repositoryLocation": "$SPLUNK_HOME/etc/deployment-apps",
                "targetRepositoryLocation": "$SPLUNK_HOME/etc/apps",
                "endpoint": "$deploymentServerUri$/services/streams/deployment",
                "filterType": "whitelist",
            },
        }
    ]
}

_SC_APPS = {
    "entry": [
        {
            "name": "Splunk_TA_nix",
            "content": {
                "restartSplunkd": False,
                "stateOnClient": "enabled",
            },
        },
        {
            "name": "my_custom_app",
            "content": {
                "restartSplunkd": True,
                "stateOnClient": "enabled",
            },
        },
    ]
}


@patch(_PATCH)
def test_serverclasses_get(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    def route_get(path: str, **kw: Any) -> MagicMock:
        if "/apps" in path:
            return _json_resp(_SC_APPS)
        return _json_resp(_SC_DETAIL)

    svc.get.side_effect = route_get

    result = CliRunner().invoke(
        cli, ["--json", "server", "serverclasses", "get", "linux_forwarders"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "linux_forwarders"
    assert data[0]["restartSplunkd"] is True
    assert data[0]["repositoryLocation"] == "$SPLUNK_HOME/etc/deployment-apps"
    assert data[0]["filterType"] == "whitelist"
    # Apps included
    apps = data[0]["apps"]
    assert len(apps) == 2
    assert apps[0]["app"] == "Splunk_TA_nix"
    assert apps[1]["app"] == "my_custom_app"
    assert apps[1]["restartSplunkd"] is True


@patch(_PATCH)
def test_serverclasses_get_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(404, "Not Found")

    result = CliRunner().invoke(
        cli, ["--json", "server", "serverclasses", "get", "nonexistent"]
    )
    assert result.exit_code == 1


@patch(_PATCH)
def test_serverclasses_get_disabled(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, "Deployment server is not enabled")

    result = CliRunner().invoke(
        cli, ["--json", "server", "serverclasses", "get", "something"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "disabled"


@patch(_PATCH)
def test_serverclasses_get_apps_fail_gracefully(mock_gc: MagicMock) -> None:
    """If the apps sub-endpoint errors, get still returns the serverclass."""
    svc = mock_gc.return_value.service

    def route_get(path: str, **kw: Any) -> MagicMock:
        if "/apps" in path:
            raise _http_error(500, "Internal error")
        return _json_resp(_SC_DETAIL)

    svc.get.side_effect = route_get

    result = CliRunner().invoke(
        cli, ["--json", "server", "serverclasses", "get", "linux_forwarders"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "linux_forwarders"
    assert data[0]["apps"] == []


# ---- serverclasses reload ----


@patch(_PATCH)
def test_serverclasses_reload_dry_run(mock_gc: MagicMock) -> None:
    """Without --yes, reload shows dry-run preview."""
    result = CliRunner().invoke(
        cli, ["server", "serverclasses", "reload", "linux_forwarders"]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch(_PATCH)
def test_serverclasses_reload_apply(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(
        cli, ["--yes", "server", "serverclasses", "reload", "linux_forwarders"]
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    assert "reloaded" in result.stderr.lower() or "reloaded" in result.output.lower()


@patch(_PATCH)
def test_serverclasses_reload_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.side_effect = _http_error(404, "Not Found")

    result = CliRunner().invoke(
        cli, ["--yes", "server", "serverclasses", "reload", "nonexistent"]
    )
    assert result.exit_code == 1


@patch(_PATCH)
def test_serverclasses_reload_disabled(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.side_effect = _http_error(503, "Deployment server is not enabled")

    result = CliRunner().invoke(
        cli, ["--yes", "server", "serverclasses", "reload", "something"]
    )
    assert result.exit_code == 1
