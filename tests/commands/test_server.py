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


# ---------------------------------------------------------------------------
# server cluster
# ---------------------------------------------------------------------------


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


@patch(_PATCH)
def test_cluster_disabled(mock_gc: MagicMock) -> None:
    """503 with 'not enabled' -> clean disabled report, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(
        503, "Cluster manager is not enabled on this node"
    )

    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["mode"] == "disabled"


def _json_resp(data: dict[str, Any]) -> MagicMock:
    """Build a MagicMock response with JSON body."""
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


_CLUSTER_INFO = {
    "entry": [
        {
            "content": {
                "label": "cluster-mgr",
                "mode": "manager",
                "replication_factor_met": True,
                "search_factor_met": True,
                "rolling_restart_flag": False,
                "maintenance_mode": False,
            }
        }
    ],
}
_CLUSTER_PEERS = {
    "entry": [
        {
            "name": "GUID-1",
            "content": {
                "label": "idx1",
                "status": "Up",
                "site": "default",
                "search_state": "Searchable",
                "replication_count": 1,
                "bucket_count": 42,
            },
        },
        {
            "name": "GUID-2",
            "content": {
                "label": "idx2",
                "status": "Down",
                "site": "default",
                "search_state": "Unsearchable",
                "replication_count": 0,
                "bucket_count": 0,
            },
        },
    ],
}


@patch(_PATCH)
def test_cluster_populated(mock_gc: MagicMock) -> None:
    """Populated cluster health with peers."""
    svc = mock_gc.return_value.service
    info_resp, peers_resp = _json_resp(_CLUSTER_INFO), _json_resp(_CLUSTER_PEERS)

    def route_get(path: str, **kw: Any) -> MagicMock:
        return peers_resp if "peers" in path else info_resp

    svc.get.side_effect = route_get

    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    # First row is cluster overview
    assert data[0]["mode"] == "manager"
    assert data[0]["replication_factor_met"] is True
    assert data[0]["search_factor_met"] is True
    # Peers follow
    assert len(data) == 3
    assert data[1]["label"] == "idx1"
    assert data[1]["status"] == "Up"
    assert data[2]["label"] == "idx2"
    assert data[2]["status"] == "Down"


@patch(_PATCH)
def test_cluster_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 on cluster endpoint propagates to F1 classifier (not swallowed)."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 1


@patch(_PATCH)
def test_cluster_manager_fallback(mock_gc: MagicMock) -> None:
    """Falls back from cluster/manager to cluster/master on 404."""
    svc = mock_gc.return_value.service
    info_resp = _json_resp(_CLUSTER_INFO)
    peers_resp = _json_resp({"entry": []})
    call_count = 0

    def route_get(path: str, **kw: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if "cluster/manager" in path and "info" in path and call_count == 1:
            raise _http_error(404, "Not Found")
        return peers_resp if "peers" in path else info_resp

    svc.get.side_effect = route_get
    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["mode"] == "manager"


# ---------------------------------------------------------------------------
# server shcluster
# ---------------------------------------------------------------------------


@patch(_PATCH)
def test_shcluster_disabled(mock_gc: MagicMock) -> None:
    """503 with 'not enabled' -> clean disabled report, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(
        503, "Search Head Clustering is not enabled on this node"
    )

    result = CliRunner().invoke(cli, ["--json", "server", "shcluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["mode"] == "disabled"


@patch(_PATCH)
def test_shcluster_populated(mock_gc: MagicMock) -> None:
    """Populated SH cluster with captain and members."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(
        {
            "entry": [
                {
                    "content": {
                        "captain": {
                            "label": "sh1",
                            "id": "GUID-C1",
                            "dynamic_captain": True,
                            "elected_captain": 1719878400,
                        },
                        "peers": {
                            "GUID-M1": {
                                "label": "sh1",
                                "status": "Up",
                                "site": "default",
                                "out_of_sync_node": False,
                            },
                            "GUID-M2": {
                                "label": "sh2",
                                "status": "Up",
                                "site": "default",
                                "out_of_sync_node": False,
                            },
                        },
                    }
                }
            ]
        }
    )
    result = CliRunner().invoke(cli, ["--json", "server", "shcluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["captain"] == "sh1"
    assert data[0]["dynamic_captain"] is True
    assert len(data) == 3
    assert data[1]["label"] == "sh1"
    assert data[2]["label"] == "sh2"


@patch(_PATCH)
def test_shcluster_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 on shcluster endpoint propagates to F1 classifier."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "shcluster"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# server deployment
# ---------------------------------------------------------------------------


@patch(_PATCH)
def test_deployment_no_clients(mock_gc: MagicMock) -> None:
    """No deployment clients -> clean empty report, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": [], "paging": {"total": 0}})
    result = CliRunner().invoke(cli, ["--json", "server", "deployment"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "no_clients"


@patch(_PATCH)
def test_deployment_populated(mock_gc: MagicMock) -> None:
    """Deployment server with clients and check-in times."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(
        {
            "entry": [
                {
                    "name": "fwd1.example.com",
                    "content": {
                        "hostname": "fwd1",
                        "ip": "10.0.0.1",
                        "clientName": "fwd1",
                        "phoneHomeTime": "2026-07-01T00:00:00+00:00",
                        "averagePhoneHomeInterval": 30,
                    },
                },
                {
                    "name": "fwd2.example.com",
                    "content": {
                        "hostname": "fwd2",
                        "ip": "10.0.0.2",
                        "clientName": "fwd2",
                        "phoneHomeTime": "2026-06-30T00:00:00+00:00",
                        "averagePhoneHomeInterval": 60,
                    },
                },
            ],
            "paging": {"total": 2},
        }
    )
    result = CliRunner().invoke(cli, ["--json", "server", "deployment"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["client"] == "fwd1"
    assert data[0]["last_phone_home"] == "2026-07-01T00:00:00+00:00"
    assert data[1]["client"] == "fwd2"


@patch(_PATCH)
def test_deployment_not_enabled(mock_gc: MagicMock) -> None:
    """503 when deployment server not enabled -> clean disabled, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, "Deployment server is not enabled")

    result = CliRunner().invoke(cli, ["--json", "server", "deployment"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "disabled"


@patch(_PATCH)
def test_deployment_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 on deployment endpoint propagates to F1 classifier."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "deployment"])
    assert result.exit_code == 1
