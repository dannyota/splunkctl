"""Tests for inputs commands."""

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_input(
    name: str,
    kind: str,
    content: dict[str, Any] | None = None,
) -> MagicMock:
    inp = MagicMock()
    inp.name = name
    inp.kind = kind
    inp.content = content or {
        "disabled": "0",
        "index": "main",
        "sourcetype": "syslog",
    }
    return inp


def _setup_mock(
    mock_gc: MagicMock,
    inputs: list[MagicMock] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.inputs.list.return_value = inputs or []
    mock_gc.return_value.service = mock_svc
    return mock_svc


@patch("splunkctl.commands.inputs.get_client")
def test_list_all(mock_gc: MagicMock) -> None:
    inp1 = _mock_input("/var/log/syslog", "monitor")
    inp2 = _mock_input("9514", "udp")
    _setup_mock(mock_gc, [inp1, inp2])

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inputs", "list"])
    assert result.exit_code == 0
    assert "/var/log/syslog" in result.output
    assert "9514" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_list_filter_kind(mock_gc: MagicMock) -> None:
    inp1 = _mock_input("/var/log/syslog", "monitor")
    inp2 = _mock_input("9514", "udp")
    _setup_mock(mock_gc, [inp1, inp2])

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inputs", "list", "--kind", "monitor"])
    assert result.exit_code == 0
    assert "/var/log/syslog" in result.output
    assert "9514" not in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_list_empty(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inputs", "list"])
    assert result.exit_code == 0


@patch("splunkctl.commands.inputs.get_client")
def test_get_found(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "inputs", "get", "/var/log/syslog"])
    assert result.exit_code == 0
    assert "/var/log/syslog" in result.output
    assert "monitor" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_get_not_found(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(cli, ["inputs", "get", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_create_dry_run(mock_gc: MagicMock) -> None:
    mock_svc = _setup_mock(mock_gc)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inputs", "create", "--name", "/var/log/test", "--kind", "monitor"],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_svc.inputs.create.assert_not_called()


@patch("splunkctl.commands.inputs.get_client")
def test_create_applies(mock_gc: MagicMock) -> None:
    mock_svc = _setup_mock(mock_gc)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "inputs",
            "create",
            "--name",
            "/var/log/test",
            "--kind",
            "monitor",
            "--index",
            "main",
        ],
    )
    assert result.exit_code == 0
    mock_svc.inputs.create.assert_called_once_with(
        "/var/log/test", "monitor", index="main"
    )


@patch("splunkctl.commands.inputs.get_client")
def test_create_all_options(mock_gc: MagicMock) -> None:
    mock_svc = _setup_mock(mock_gc)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "inputs",
            "create",
            "--name",
            "/var/log/test",
            "--kind",
            "monitor",
            "--index",
            "main",
            "--sourcetype",
            "syslog",
            "--disabled",
        ],
    )
    assert result.exit_code == 0
    mock_svc.inputs.create.assert_called_once_with(
        "/var/log/test",
        "monitor",
        index="main",
        sourcetype="syslog",
        disabled=True,
    )


@patch("splunkctl.commands.inputs.get_client")
def test_update_dry_run(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inputs", "update", "/var/log/syslog", "--index", "security"],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    inp.update.assert_not_called()


@patch("splunkctl.commands.inputs.get_client")
def test_update_applies(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "inputs",
            "update",
            "/var/log/syslog",
            "--index",
            "security",
        ],
    )
    assert result.exit_code == 0
    inp.update.assert_called_once_with(index="security")


@patch("splunkctl.commands.inputs.get_client")
def test_update_enable_flag(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "inputs", "update", "/var/log/syslog", "--enabled"],
    )
    assert result.exit_code == 0
    inp.update.assert_called_once_with(disabled=False)


@patch("splunkctl.commands.inputs.get_client")
def test_update_no_options(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc)

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "update", "test"])
    assert result.exit_code != 0
    assert "No update options" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_update_not_found(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "inputs", "update", "nonexistent", "--index", "main"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc)

    runner = CliRunner()
    result = runner.invoke(cli, ["inputs", "delete", "test"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_delete_applies(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "delete", "/var/log/syslog"])
    assert result.exit_code == 0
    inp.delete.assert_called_once()


@patch("splunkctl.commands.inputs.get_client")
def test_delete_not_found(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "delete", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_enable_applies(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "enable", "/var/log/syslog"])
    assert result.exit_code == 0
    inp.enable.assert_called_once()


@patch("splunkctl.commands.inputs.get_client")
def test_enable_not_found(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "enable", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.inputs.get_client")
def test_disable_applies(mock_gc: MagicMock) -> None:
    inp = _mock_input("/var/log/syslog", "monitor")
    _setup_mock(mock_gc, [inp])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "disable", "/var/log/syslog"])
    assert result.exit_code == 0
    inp.disable.assert_called_once()


@patch("splunkctl.commands.inputs.get_client")
def test_disable_not_found(mock_gc: MagicMock) -> None:
    _setup_mock(mock_gc, [])

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "inputs", "disable", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output
