"""Tests for server topology health commands (cluster/shcluster/deployment)."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server_topology.get_client"


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


def _http_error_json(status: int, body_text: str) -> Exception:
    """Build a splunklib HTTPError with a JSON error body (live shape)."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "Service Unavailable" if status == 503 else "Error"
    resp.body.read.return_value = json.dumps(
        {"messages": [{"type": "ERROR", "text": body_text}]}
    ).encode()
    resp.headers = {}
    from splunklib.binding import HTTPError

    return HTTPError(resp)


@patch(_PATCH)
def test_cluster_disabled_detail_is_clean_message(mock_gc: MagicMock) -> None:
    """The disabled detail is the REST message text, not str(exc) bytes."""
    text = "Cluster manager is not enabled on this node"
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error_json(503, text)

    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["detail"] == text
    assert "b'" not in data[0]["detail"]


@patch(_PATCH)
def test_cluster_disabled_xml_detail_is_clean_message(mock_gc: MagicMock) -> None:
    """XML error bodies also yield just the message text."""
    text = "Cluster manager is not enabled on this node"
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, text)

    result = CliRunner().invoke(cli, ["--json", "server", "cluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["detail"] == text


@patch(_PATCH)
def test_shcluster_disabled_detail_is_clean_message(mock_gc: MagicMock) -> None:
    text = "Search Head Clustering is not enabled on this node"
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error_json(503, text)

    result = CliRunner().invoke(cli, ["--json", "server", "shcluster"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["detail"] == text


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
def test_cluster_peers_genuine_error_propagates(mock_gc: MagicMock) -> None:
    """A 401 on the peers endpoint propagates (not swallowed as best-effort)."""
    svc = mock_gc.return_value.service
    info_resp = _json_resp(_CLUSTER_INFO)

    def route_get(path: str, **kw: Any) -> MagicMock:
        if "peers" in path:
            raise _http_error(401, "Unauthorized")
        return info_resp

    svc.get.side_effect = route_get
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


# ---------------------------------------------------------------------------
# server health
# ---------------------------------------------------------------------------

_HEALTH_DETAILS = {
    "entry": [
        {
            "content": {
                "health": "yellow",
                "features": {
                    "Search Scheduler": {
                        "health": "yellow",
                        "features": {
                            "Searches Skipped": {
                                "health": "yellow",
                                "reasons": {
                                    "yellow": {
                                        "1": {
                                            "reason": "10% of searches skipped",
                                            "due_to_stanza": "feature:searches_skipped",
                                        }
                                    }
                                },
                            },
                            "Search Lag": {"health": "green"},
                        },
                    },
                    "Index Processor": {
                        "health": "green",
                        "features": {"Disk Space": {"health": "green"}},
                    },
                },
            }
        }
    ],
}


@patch(_PATCH)
def test_health_flattens_component_tree(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(_HEALTH_DETAILS)

    result = CliRunner().invoke(cli, ["--json", "server", "health"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    by_component = {r["component"]: r for r in data}
    assert by_component["splunkd"]["health"] == "yellow"
    assert by_component["Search Scheduler"]["health"] == "yellow"
    assert by_component["Search Scheduler / Searches Skipped"]["health"] == "yellow"
    assert by_component["Search Scheduler / Search Lag"]["health"] == "green"
    assert by_component["Index Processor / Disk Space"]["health"] == "green"


@patch(_PATCH)
def test_health_surfaces_reasons_for_unhealthy(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(_HEALTH_DETAILS)

    result = CliRunner().invoke(cli, ["--json", "server", "health"])
    data = json.loads(result.output)
    skipped = next(
        r for r in data if r["component"] == "Search Scheduler / Searches Skipped"
    )
    assert "10% of searches skipped" in skipped["reasons"]
    green = next(r for r in data if r["component"] == "Search Scheduler / Search Lag")
    assert green["reasons"] == ""


@patch(_PATCH)
def test_health_red_component_still_exits_zero(mock_gc: MagicMock) -> None:
    """health reports, it does not gate — red components exit 0."""
    details = {"entry": [{"content": {"health": "red", "features": {}}}]}
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(details)

    result = CliRunner().invoke(cli, ["--json", "server", "health"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0] == {"component": "splunkd", "health": "red", "reasons": ""}


# ---------------------------------------------------------------------------
# server search-peers
# ---------------------------------------------------------------------------


@patch(_PATCH)
def test_search_peers_lists_peers(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(
        {
            "entry": [
                {
                    "name": "idx1:8089",
                    "content": {
                        "peerName": "idx1",
                        "status": "Up",
                        "replicationStatus": "Successful",
                        "version": "10.4.0",
                    },
                }
            ]
        }
    )

    result = CliRunner().invoke(cli, ["--json", "server", "search-peers"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["peer"] == "idx1"
    assert data[0]["status"] == "Up"
    assert data[0]["replication_status"] == "Successful"
    assert data[0]["version"] == "10.4.0"


@patch(_PATCH)
def test_search_peers_empty_on_standalone(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "search-peers"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []
