"""Tests for alerts commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_firing(sid: str, severity: str = "4") -> MagicMock:
    firing = MagicMock()
    firing.content = {
        "trigger_time_rendered": "2026-07-02T10:00:00+0700",
        "severity": severity,
        "sid": sid,
        "actions": "",
    }
    return firing


def _mock_group(name: str, firings: list[MagicMock]) -> MagicMock:
    group = MagicMock()
    group.name = name
    group.count = len(firings)
    group.alerts = firings
    return group


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_list_rows_per_firing(mock_gc: MagicMock) -> None:
    group = _mock_group("test_alert", [_mock_firing("sid1"), _mock_firing("sid2")])
    mock_svc = MagicMock()
    mock_svc.fired_alerts = [group]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "alerts", "list"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert len(rows) == 2
    assert rows[0]["rule"] == "test_alert"
    assert rows[0]["sid"] == "sid1"
    assert rows[1]["sid"] == "sid2"
    assert rows[0]["triggered"] == "2026-07-02T10:00:00+0700"
    assert rows[0]["severity"] == "4"


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_list_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.fired_alerts = []
    mock_gc.return_value.service = mock_svc
    result = CliRunner().invoke(cli, ["--json", "alerts", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_get_multiple_firings_no_crash(mock_gc: MagicMock) -> None:
    # regression: AmbiguousReferenceException when an alert fired >1 time
    group = _mock_group("my_alert", [_mock_firing("s1"), _mock_firing("s2")])
    fired = MagicMock()
    fired.__iter__ = MagicMock(return_value=iter([group]))
    # direct item access must not be used at all (AmbiguousReferenceException)
    fired.__getitem__ = MagicMock(side_effect=AssertionError("must iterate"))
    mock_svc = MagicMock()
    mock_svc.fired_alerts = fired
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "alerts", "get", "my_alert"])
    assert result.exit_code == 0
    assert "Traceback" not in result.output
    rows = json.loads(result.stdout)
    assert [r["sid"] for r in rows] == ["s1", "s2"]


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_get_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.fired_alerts = []
    mock_gc.return_value.service = mock_svc
    result = CliRunner().invoke(cli, ["--json", "alerts", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_actions(mock_gc: MagicMock) -> None:
    stanza = MagicMock()
    stanza.name = "email"
    stanza.content = {
        "label": "Send email",
        "description": "Send an email notification",
    }
    mock_svc = MagicMock()
    mock_svc.confs.__getitem__ = MagicMock(return_value=[stanza])
    mock_gc.return_value.service = mock_svc
    result = CliRunner().invoke(cli, ["--json", "alerts", "actions"])
    assert result.exit_code == 0
    assert "email" in result.output


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["alerts", "suppress", "my_alert"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.stderr
    assert "alert.suppress" in result.stderr
    mock_gc.assert_not_called()


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_sets_saved_search_fields(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    mock_svc = MagicMock()
    mock_svc.saved_searches.__getitem__ = MagicMock(return_value=ss)
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--yes", "alerts", "suppress", "--duration", "600", "my_alert"]
    )
    assert result.exit_code == 0
    _, kwargs = ss.update.call_args
    assert kwargs["alert.suppress"] == "1"
    assert kwargs["alert.suppress.period"] == "600s"


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_missing_rule(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.saved_searches.__getitem__ = MagicMock(side_effect=KeyError("no"))
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "alerts", "suppress", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_unsuppress_clears(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    mock_svc = MagicMock()
    mock_svc.saved_searches.__getitem__ = MagicMock(return_value=ss)
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "alerts", "unsuppress", "my_alert"])
    assert result.exit_code == 0
    _, kwargs = ss.update.call_args
    assert kwargs["alert.suppress"] == "0"
