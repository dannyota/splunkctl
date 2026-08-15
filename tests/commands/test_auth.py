"""Tests for the top-level auth commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


@patch("splunkctl.commands.auth.browser_available", return_value=True)
@patch("splunkctl.commands.auth.run_login")
@patch("splunkctl.commands.auth.get_adapter")
@patch("splunkctl.commands.auth.resolve_target")
@patch("splunkctl.commands.auth.save")
def test_login_creates_session(
    mock_save: MagicMock,
    mock_rt: MagicMock,
    mock_adapter: MagicMock,
    mock_run: MagicMock,
    mock_avail: MagicMock,
) -> None:
    mock_rt.return_value = MagicMock(
        target="siem",
        profile="default",
        web_url="http://siem:8000",
        api_base="https://siem:8089",
        verify=True,
        timeout=30,
    )
    adapter = mock_adapter.return_value
    adapter.login_url.return_value = "http://siem:8000/en-US/account/login"
    adapter.extract.return_value = {"session_key": "k", "cookie": "splunkd_8000"}
    adapter.validate.return_value = "valid"
    mock_run.return_value = {"splunkd_8000": "k"}

    result = CliRunner().invoke(cli, ["auth", "login", "--target", "siem"])
    assert result.exit_code == 0, result.output
    assert mock_save.call_count == 1
    record = mock_save.call_args.args[1]
    assert record.values["session_key"] == "k"


@patch("splunkctl.commands.auth.browser_available", return_value=False)
@patch("splunkctl.commands.auth.install_hint", return_value="pip install ...")
@patch("splunkctl.commands.auth.resolve_target")
def test_login_missing_browser_fails(
    mock_rt: MagicMock, mock_hint: MagicMock, mock_avail: MagicMock
) -> None:
    mock_rt.return_value = MagicMock(
        target="siem",
        profile="default",
        web_url="x",
        api_base="y",
        verify=True,
        timeout=30,
    )
    result = CliRunner().invoke(cli, ["auth", "login", "--target", "siem"])
    assert result.exit_code == 1


@patch("splunkctl.commands.auth.resolve_target")
@patch("splunkctl.commands.auth.load", return_value=None)
def test_status_missing(mock_load: MagicMock, mock_rt: MagicMock) -> None:
    mock_rt.return_value = MagicMock(
        target="siem",
        profile="default",
        web_url="x",
        api_base="y",
        verify=True,
        timeout=30,
    )
    result = CliRunner().invoke(cli, ["--json", "auth", "status", "--target", "siem"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["target"] == "siem"
    assert data[0]["status"] == "missing"


@patch("splunkctl.commands.auth.get_adapter")
@patch("splunkctl.commands.auth.resolve_target")
def test_logout_removes_local_session(
    mock_rt: MagicMock, mock_adapter: MagicMock
) -> None:
    mock_rt.return_value = MagicMock(
        target="soar",
        profile="default",
        web_url="https://soar",
        api_base="https://soar",
        verify=True,
        timeout=30,
    )
    with (
        patch("splunkctl.commands.auth.load") as mock_load,
        patch("splunkctl.commands.auth.delete") as mock_delete,
    ):
        mock_load.return_value = MagicMock(values={"sessionid": "s", "csrftoken": "c"})
        result = CliRunner().invoke(cli, ["auth", "logout", "--target", "soar"])
        assert result.exit_code == 0, result.output
        mock_delete.assert_called_once_with("default", "soar")
