"""Tests for info command."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


@patch("splunkctl.commands.info.get_client")
def test_info_renders_server_info(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.info = {
        "serverName": "test-srv",
        "version": "10.4.0",
        "build": "abc123",
        "os_name": "Linux",
        "cpu_arch": "x86_64",
        "licenseState": "OK",
        "mode": "normal",
        "guid": "1234-5678",
    }
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "info"])
    assert result.exit_code == 0
    assert "test-srv" in result.output
    assert "10.4.0" in result.output
