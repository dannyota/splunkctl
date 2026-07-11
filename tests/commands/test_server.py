"""Tests for server commands."""

import json
from typing import Any
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


def _resp(data: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


@patch(_PATCH)
def test_license_usage_daily_volume(mock_gc: MagicMock) -> None:
    """--usage shows today's indexed volume vs quota and soonest expiry."""
    svc = mock_gc.return_value.service

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        if "licenser/usage" in path:
            return _resp(
                {
                    "entry": [
                        {
                            "name": "license_usage",
                            "content": {
                                "quota": 524288000,
                                "slaves_usage_bytes": 262144000,
                                "peers_usage_bytes": 0,
                            },
                        }
                    ]
                }
            )
        return _resp(
            {
                "entry": [
                    {
                        "name": "AAA",
                        "content": {
                            "type": "enterprise",
                            "status": "VALID",
                            "quota": 524288000,
                            "expiration_time": 1788934111,
                            "label": "Splunk Enterprise",
                        },
                    },
                    {
                        "name": "FFF",
                        "content": {
                            "type": "forwarder",
                            "status": "VALID",
                            "quota": 1048576,
                            "expiration_time": 2147483647,
                            "label": "Splunk Forwarder",
                        },
                    },
                ]
            }
        )

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "license", "--usage"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    row = data[0]
    assert row["used"] == "250.0 MB"
    assert row["quota"] == "500.0 MB"
    assert row["pct_used"] == 50.0
    assert row["licenses_valid"] == 2
    assert row["soonest_expiry"].startswith("2026-")


@patch(_PATCH)
def test_license_usage_perpetual_only_never_expires(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        if "licenser/usage" in path:
            return _resp(
                {
                    "entry": [
                        {
                            "name": "license_usage",
                            "content": {"quota": 100, "slaves_usage_bytes": 0},
                        }
                    ]
                }
            )
        return _resp(
            {
                "entry": [
                    {
                        "name": "FFF",
                        "content": {
                            "type": "free",
                            "status": "VALID",
                            "quota": 100,
                            "expiration_time": 2147483647,
                            "label": "Splunk Free",
                        },
                    }
                ]
            }
        )

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "license", "--usage"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["pct_used"] == 0.0
    assert row["soonest_expiry"] == "never"
