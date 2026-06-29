"""Tests for alerts commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_alert(name: str, count: int = 1, severity: str = "3") -> MagicMock:
    alert = MagicMock()
    alert.name = name
    alert.count = count
    alert.content = {
        "triggered_alert_count": str(count),
        "triggered_time": "1719600000",
        "severity": severity,
    }
    return alert


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_list(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.fired_alerts = [_mock_alert("test_alert", count=3)]
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "alerts", "list"])
    assert result.exit_code == 0
    assert "test_alert" in result.output
    assert "3" in result.output


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_list_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.fired_alerts = []
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "alerts", "list"])
    assert result.exit_code == 0


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_get(mock_gc: MagicMock) -> None:
    alert = _mock_alert("my_alert", count=5, severity="4")
    mock_svc = MagicMock()
    mock_svc.fired_alerts.__getitem__ = MagicMock(return_value=alert)
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "alerts", "get", "my_alert"])
    assert result.exit_code == 0
    assert "my_alert" in result.output


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_get_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.fired_alerts.__getitem__ = MagicMock(side_effect=KeyError("nope"))
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "alerts", "get", "nope"])
    assert result.exit_code != 0


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
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "alerts", "actions"])
    assert result.exit_code == 0
    assert "email" in result.output


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["alerts", "suppress", "my_alert"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "alerts", "suppress", "--duration", "7200", "my_alert"],
    )
    assert result.exit_code == 0
    mock_svc.post.assert_called_once()
    args = mock_svc.post.call_args
    assert "my_alert" in args[0][0]
    assert args[1]["suppress"] == "1"
    assert args[1]["expiration"] == "7200"


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_suppress_default_duration(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "alerts", "suppress", "my_alert"])
    assert result.exit_code == 0
    args = mock_svc.post.call_args
    assert args[1]["expiration"] == "3600"
