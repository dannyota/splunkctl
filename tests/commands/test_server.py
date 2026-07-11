"""Tests for server commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server.get_client"


@patch(_PATCH)
def test_messages_list(mock_gc: MagicMock) -> None:
    msg = MagicMock()
    msg.name = "warn_disk"
    msg.content = {
        "severity": "warn",
        "message": "Disk low",
        "timeCreated_iso": "2026-07-01T00:00:00Z",
    }
    svc = mock_gc.return_value.service
    svc.messages.list.return_value = [msg]

    result = CliRunner().invoke(cli, ["--json", "server", "messages"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "warn_disk"
    assert data[0]["severity"] == "warn"


@patch(_PATCH)
def test_messages_dismiss(mock_gc: MagicMock) -> None:
    msg = MagicMock()
    svc = mock_gc.return_value.service
    svc.messages.__getitem__.return_value = msg

    result = CliRunner().invoke(
        cli,
        ["--yes", "server", "messages", "--dismiss", "warn_disk"],
    )
    assert result.exit_code == 0
    msg.delete.assert_called_once()


@patch(_PATCH)
def test_messages_dismiss_not_found_json_envelope(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.messages.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(
        cli,
        ["--yes", "--json", "server", "messages", "--dismiss", "nope"],
    )
    assert result.exit_code == 1
    # stderr carries the guard's "Applying: ..." banner ahead of the envelope
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "not_found"


@patch(_PATCH)
def test_license_pools(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(
        {
            "entry": [
                {
                    "name": "auto",
                    "content": {
                        "used_bytes": 1048576,
                        "effective_quota": 524288000,
                    },
                }
            ]
        }
    ).encode()
    svc.get.return_value = resp

    result = CliRunner().invoke(cli, ["--json", "server", "license"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["title"] == "auto"


@patch(_PATCH)
def test_kvstore_status_ready(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(
        {
            "entry": [
                {
                    "content": {
                        "current": {
                            "status": "ready",
                            "port": 8191,
                            "version": "4.4",
                            "storageEngine": "wiredTiger",
                            "dbPath": "/opt/splunk/var/lib/splunk/kvstore/mongo",
                        }
                    }
                }
            ]
        }
    ).encode()
    svc.get.return_value = resp

    result = CliRunner().invoke(cli, ["--json", "server", "kvstore"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0] == {
        "status": "ready",
        "port": 8191,
        "version": "4.4",
        "storage_engine": "wiredTiger",
        "db_path": "/opt/splunk/var/lib/splunk/kvstore/mongo",
    }


@patch(_PATCH)
def test_kvstore_status_failed(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(
        {
            "entry": [
                {
                    "content": {
                        "current": {
                            "status": "failed",
                            "port": 8191,
                            "storageEngine": "wiredTiger",
                            "disabled": False,
                        }
                    }
                }
            ]
        }
    ).encode()
    svc.get.return_value = resp

    result = CliRunner().invoke(cli, ["--json", "server", "kvstore"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "failed"


@patch(_PATCH)
def test_kvstore_status_missing_current(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    resp = MagicMock()
    resp.body.read.return_value = json.dumps({"entry": [{"content": {}}]}).encode()
    svc.get.return_value = resp

    result = CliRunner().invoke(cli, ["--json", "server", "kvstore"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "unknown"
