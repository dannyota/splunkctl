"""Tests for doctor command."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.doctor.get_client"


def _mock_service() -> MagicMock:
    svc = MagicMock()
    svc.username = "admin"
    svc.host = "splunk.example.com"
    svc.info = {
        "version": "10.4.0",
        "os_name": "Linux",
        "os_version": "5.15",
        "mode": "normal",
        "licenseState": "OK",
        "isTrial": "0",
    }

    health_resp = MagicMock()
    health_resp.body.read.return_value = json.dumps(
        {"entry": [{"content": {"health": "green"}}]}
    ).encode()
    svc.get.return_value = health_resp

    svc.messages.list.return_value = []

    user = MagicMock()
    user.content = {
        "roles": ["admin"],
        "capabilities": [
            "search",
            "admin_all_objects",
            "edit_user",
            "edit_roles",
            "edit_tcp",
            "edit_monitor",
            "list_inputs",
            "rest_apps_management",
            "change_own_password",
        ],
    }
    svc.users.__getitem__.return_value = user

    web_entity = MagicMock()
    web_entity.__getitem__ = MagicMock(
        side_effect=lambda k: "8000" if k == "httpport" else "",
    )
    web_entity.content = {"enableSplunkWebSSL": "0"}
    svc.confs.__getitem__.return_value.__getitem__.return_value = web_entity

    return svc


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_all_pass(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "PASS  REST API reachable" in result.output
    assert "PASS  Authenticated" in result.output
    assert "PASS  cap:search" in result.output
    assert "0 failures" in result.output


@patch(_PATCH)
def test_doctor_connection_fail(mock_gc: MagicMock) -> None:
    mock_client = MagicMock()
    type(mock_client).service = property(
        lambda self: (_ for _ in ()).throw(
            ConnectionError("refused"),
        ),
    )
    mock_gc.return_value = mock_client

    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code != 0
    assert "FAIL" in result.output


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_json_output(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert result.exit_code == 0
    assert '"check"' in result.output
    assert '"REST API reachable"' in result.output
    assert '"cap:search"' in result.output
