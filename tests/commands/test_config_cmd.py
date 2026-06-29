"""Tests for config commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def test_config_init(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\n",
    )
    assert result.exit_code == 0
    assert cfg.exists()
    assert "Config saved" in result.output


def test_config_show() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "config", "show"])
    assert result.exit_code == 0
    assert "host" in result.output


def test_config_show_redacts_password(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("host: h\npassword: secret123\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--config", str(cfg), "config", "show"])
    assert result.exit_code == 0
    assert "secret123" not in result.output


@patch("splunkctl.commands.config_cmd.SplunkClient")
def test_config_test_success(mock_cls: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.info = {"serverName": "test-srv", "version": "10.4.0"}
    mock_cls.return_value = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "test"])
    assert result.exit_code == 0
    assert "OK" in result.output


@patch("splunkctl.commands.config_cmd.SplunkClient")
def test_config_test_failure(mock_cls: MagicMock) -> None:
    mock_cls.return_value.service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("refused"))
    )
    mock_cls.side_effect = None
    mock_instance = MagicMock()
    type(mock_instance).service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("refused"))
    )
    mock_cls.return_value = mock_instance
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "test"])
    assert result.exit_code != 0
