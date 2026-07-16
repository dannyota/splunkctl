"""Tests for server workloads commands (pools, rules, status)."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server_workloads.get_client"


def _http_error(status: int, body_text: str) -> Exception:
    """Build a splunklib HTTPError with the given status and body."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "Not Found" if status == 404 else "Error"
    resp.body.read.return_value = (
        f"<response><messages><msg>{body_text}</msg></messages></response>".encode()
    )
    resp.headers = {}
    from splunklib.binding import HTTPError

    return HTTPError(resp)


def _json_resp(data: dict[str, Any]) -> MagicMock:
    """Build a MagicMock response with JSON body."""
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


# ---------------------------------------------------------------------------
# server workloads pools
# ---------------------------------------------------------------------------

_POOLS = {
    "entry": [
        {
            "name": "high_perf",
            "content": {
                "cpu_weight": "80",
                "mem_weight": "80",
                "default_category": "search",
                "category": "search",
            },
        },
        {
            "name": "low_perf",
            "content": {
                "cpu_weight": "20",
                "mem_weight": "20",
                "default_category": "misc",
                "category": "misc",
            },
        },
    ],
}


@patch(_PATCH)
def test_pools_lists_pools(mock_gc: MagicMock) -> None:
    """Populated pools render with CPU/memory weights."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(_POOLS)

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "pools"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "high_perf"
    assert data[0]["cpu_weight"] == "80"
    assert data[0]["mem_weight"] == "80"
    assert data[1]["name"] == "low_perf"
    assert data[1]["cpu_weight"] == "20"


@patch(_PATCH)
def test_pools_empty(mock_gc: MagicMock) -> None:
    """No pools configured -> empty result, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "pools"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@patch(_PATCH)
def test_pools_not_available_404(mock_gc: MagicMock) -> None:
    """404 -> clean not-available status, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(404, "Not Found")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "pools"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_available"


@patch(_PATCH)
def test_pools_not_available_503(mock_gc: MagicMock) -> None:
    """503 with 'not enabled' -> clean not-available status, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, "Workload management is not enabled")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "pools"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_available"


@patch(_PATCH)
def test_pools_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 propagates to F1 classifier (not swallowed)."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "pools"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# server workloads rules
# ---------------------------------------------------------------------------

_RULES = {
    "entry": [
        {
            "name": "abort_long_searches",
            "content": {
                "predicate": "runtime>600",
                "workload_pool": "low_perf",
                "action": "abort",
                "order": "1",
                "schedule": "always_on",
            },
        },
    ],
}


@patch(_PATCH)
def test_rules_lists_rules(mock_gc: MagicMock) -> None:
    """Populated rules render with predicate and pool."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(_RULES)

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "rules"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "abort_long_searches"
    assert data[0]["predicate"] == "runtime>600"
    assert data[0]["workload_pool"] == "low_perf"
    assert data[0]["action"] == "abort"


@patch(_PATCH)
def test_rules_empty(mock_gc: MagicMock) -> None:
    """No rules configured -> empty result, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "rules"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@patch(_PATCH)
def test_rules_not_available_404(mock_gc: MagicMock) -> None:
    """404 -> clean not-available status, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(404, "Not Found")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "rules"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_available"


@patch(_PATCH)
def test_rules_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 propagates to F1 classifier."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "rules"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# server workloads status
# ---------------------------------------------------------------------------


@patch(_PATCH)
def test_status_shows_current_load(mock_gc: MagicMock) -> None:
    """Status endpoint returns enabled state."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(
        {
            "entry": [
                {
                    "content": {
                        "status": "enabled",
                        "admission_rules_enabled": True,
                    }
                }
            ],
        }
    )

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "enabled"
    assert data[0]["admission_rules_enabled"] is True


@patch(_PATCH)
def test_status_with_pool_utilisation(mock_gc: MagicMock) -> None:
    """Status with nested pool utilisation data."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp(
        {
            "entry": [
                {
                    "content": {
                        "status": "enabled",
                        "admission_rules_enabled": True,
                        "pools": {
                            "high_perf": {
                                "cpu_usage": "45%",
                                "mem_usage": "60%",
                                "search_count": 12,
                            },
                        },
                    }
                }
            ],
        }
    )

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "enabled"
    pools = data[0]["pools"]
    assert len(pools) == 1
    assert pools[0]["pool"] == "high_perf"
    assert pools[0]["cpu_usage"] == "45%"


@patch(_PATCH)
def test_status_empty_entries(mock_gc: MagicMock) -> None:
    """No entries in status response -> not_available, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _json_resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_available"


@patch(_PATCH)
def test_status_not_available_404(mock_gc: MagicMock) -> None:
    """404 -> clean not-available status, exit 0."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(404, "Not Found")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_available"


@patch(_PATCH)
def test_status_genuine_error(mock_gc: MagicMock) -> None:
    """A 401 propagates to F1 classifier."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(401, "Unauthorized")

    result = CliRunner().invoke(cli, ["--json", "server", "workloads", "status"])
    assert result.exit_code == 1
