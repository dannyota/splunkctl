"""Tests for the es correlations (correlation search management) commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.es.get_client"


def _mock_svc_with_es() -> MagicMock:
    """A service mock where the ES app entity fetch succeeds."""
    svc = MagicMock()
    svc.apps.__getitem__.return_value = MagicMock()
    return svc


def _mock_svc_without_es() -> MagicMock:
    """A service mock where the ES app entity fetch raises KeyError."""
    svc = MagicMock()
    svc.apps.__getitem__.side_effect = KeyError("no such app")
    return svc


def _mock_saved_search(
    name: str,
    *,
    disabled: str = "0",
    security_domain: str = "access",
    severity: str = "3",
    cron: str = "*/5 * * * *",
    next_time: str = "2026-07-16T10:00:00",
    description: str = "",
    search: str = "| tstats count",
) -> MagicMock:
    """Build a mocked saved-search entity for correlation tests."""
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "disabled": disabled,
        "action.correlationsearch.label": security_domain,
        "alert.severity": severity,
        "cron_schedule": cron,
        "next_scheduled_time": next_time,
        "is_scheduled": "1",
        "search": search,
        "description": description,
        "actions": "notable",
        "dispatch.earliest_time": "-24h",
        "dispatch.latest_time": "now",
    }
    ss.access = {
        "app": "SplunkEnterpriseSecuritySuite",
        "owner": "admin",
        "sharing": "app",
    }
    ss.update.return_value = ss
    return ss


# --- correlations list ---


@patch(_PATCH)
def test_corr_list_returns_rows(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = [
        _mock_saved_search("Brute Force", security_domain="access"),
        _mock_saved_search(
            "Malware Detected", security_domain="endpoint", disabled="1"
        ),
    ]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--json", "es", "correlations", "list"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 2
    assert rows[0]["name"] == "Brute Force"
    assert rows[0]["enabled"] == "1"
    assert rows[1]["name"] == "Malware Detected"
    assert rows[1]["enabled"] == "0"
    svc.saved_searches.list.assert_called_once_with(
        app="SplunkEnterpriseSecuritySuite", owner="-"
    )


@patch(_PATCH)
def test_corr_list_filter_enabled(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = [
        _mock_saved_search("Brute Force", disabled="0"),
        _mock_saved_search("Malware Detected", disabled="1"),
    ]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "correlations", "list", "--enabled"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["name"] == "Brute Force"


@patch(_PATCH)
def test_corr_list_filter_disabled(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = [
        _mock_saved_search("Brute Force", disabled="0"),
        _mock_saved_search("Malware Detected", disabled="1"),
    ]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "correlations", "list", "--disabled"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["name"] == "Malware Detected"


@patch(_PATCH)
def test_corr_list_filter_security_domain(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = [
        _mock_saved_search("Brute Force", security_domain="access"),
        _mock_saved_search("DNS Exfil", security_domain="network"),
    ]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "correlations", "list", "--security-domain", "network"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["name"] == "DNS Exfil"


@patch(_PATCH)
def test_corr_list_empty(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = []
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["es", "correlations", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"

    result = CliRunner().invoke(
        cli, ["--format", "table", "es", "correlations", "list"]
    )
    assert result.exit_code == 0
    assert "No correlation searches found" in result.stderr


@patch(_PATCH)
def test_corr_list_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(cli, ["--json", "es", "correlations", "list"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"
    assert "SplunkEnterpriseSecuritySuite" in payload["error"]["message"]


# --- correlations get ---


@patch(_PATCH)
def test_corr_get_returns_detail(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    ss = _mock_saved_search(
        "Brute Force",
        security_domain="access",
        description="Detects brute force attempts",
    )
    svc.saved_searches.list.return_value = [ss]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "correlations", "get", "Brute Force"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    detail = rows[0]
    assert detail["name"] == "Brute Force"
    assert detail["security_domain"] == "access"
    assert detail["description"] == "Detects brute force attempts"
    assert detail["enabled"] == "1"
    assert "search" in detail


@patch(_PATCH)
def test_corr_get_not_found(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = []
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "correlations", "get", "Nonexistent Rule"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"
    assert "Nonexistent Rule" in payload["error"]["message"]


# --- correlations enable ---


@patch(_PATCH)
def test_corr_enable_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["es", "correlations", "enable", "Brute Force"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "Brute Force" in result.stderr
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_corr_enable_applies(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    ss = _mock_saved_search("Brute Force", disabled="1")
    svc.saved_searches.list.return_value = [ss]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "es", "correlations", "enable", "Brute Force"]
    )
    assert result.exit_code == 0
    ss.update.assert_called_once_with(disabled="0", is_scheduled="1")
    assert "Enabled 1 correlation" in result.stderr


@patch(_PATCH)
def test_corr_enable_multiple(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    ss1 = _mock_saved_search("Brute Force", disabled="1")
    ss2 = _mock_saved_search("DNS Exfil", disabled="1")
    # list is called once per name in the loop
    svc.saved_searches.list.side_effect = [[ss1], [ss2]]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "es", "correlations", "enable", "Brute Force", "DNS Exfil"]
    )
    assert result.exit_code == 0
    assert ss1.update.called
    assert ss2.update.called
    assert "Enabled 2 correlation" in result.stderr


@patch(_PATCH)
def test_corr_enable_not_found(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.saved_searches.list.return_value = []
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "es", "correlations", "enable", "Nonexistent"]
    )
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "not_found"


# --- correlations disable ---


@patch(_PATCH)
def test_corr_disable_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["es", "correlations", "disable", "Brute Force"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_corr_disable_applies(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    ss = _mock_saved_search("Brute Force", disabled="0")
    svc.saved_searches.list.return_value = [ss]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "es", "correlations", "disable", "Brute Force"]
    )
    assert result.exit_code == 0
    ss.update.assert_called_once_with(disabled="1")
    assert "Disabled 1 correlation" in result.stderr


@patch(_PATCH)
def test_corr_disable_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(
        cli,
        ["--yes", "--json", "es", "correlations", "disable", "Brute Force"],
    )
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "not_found"


def test_corr_enable_missing_names_is_usage_error() -> None:
    result = CliRunner().invoke(cli, ["--yes", "es", "correlations", "enable"])
    assert result.exit_code == 2


def test_corr_disable_missing_names_is_usage_error() -> None:
    result = CliRunner().invoke(cli, ["--yes", "es", "correlations", "disable"])
    assert result.exit_code == 2


# --- commands --json includes correlations ---


def test_commands_json_includes_correlations_group() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.output)
    es_node = next(c for c in tree["commands"] if c["name"] == "es")
    corr_node = next(c for c in es_node["subcommands"] if c["name"] == "correlations")
    sub_names = [c["name"] for c in corr_node["subcommands"]]
    assert set(sub_names) == {"list", "get", "enable", "disable"}
    enable_node = next(c for c in corr_node["subcommands"] if c["name"] == "enable")
    assert enable_node.get("guarded") is True
    disable_node = next(c for c in corr_node["subcommands"] if c["name"] == "disable")
    assert disable_node.get("guarded") is True
