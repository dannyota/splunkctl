"""Tests for HEC token commands."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.hec.get_client"


def _mock_token(
    name: str = "my_token",
    token: str = "abc-123",  # noqa: S107
    index: str = "main",
) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.content = {
        "token": token,
        "index": index,
        "indexes": "main,_internal",
        "sourcetype": "",
        "disabled": "0",
        "useACK": "false",
    }
    return t


@patch("splunkctl.commands.hec.get_client")
def test_list_hec(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.hec_tokens.list.return_value = [_mock_token()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "hec", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "my_token"
    assert data[0]["token"] == "abc-123"


@patch("splunkctl.commands.hec.get_client")
def test_list_hec_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.hec_tokens.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["hec", "list"])
    assert result.exit_code == 0
    # piped empty result is a valid JSON payload, not a bare message
    assert result.stdout.strip() == "[]"

    result = CliRunner().invoke(cli, ["--format", "table", "hec", "list"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "No HEC tokens found" in result.stderr


@patch("splunkctl.commands.hec.get_client")
def test_get_hec(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.hec_tokens.__getitem__.return_value = _mock_token()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "hec", "get", "my_token"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "my_token"
    assert data[0]["index"] == "main"


@patch("splunkctl.commands.hec.get_client")
def test_get_hec_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.hec_tokens.__getitem__.side_effect = KeyError("nope")
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["hec", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


def test_create_dry_run() -> None:
    result = CliRunner().invoke(cli, ["hec", "create", "--name", "new_token"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.hec.get_client")
def test_create_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--yes", "hec", "create", "--name", "new_token", "--index", "main"]
    )
    assert result.exit_code == 0
    assert "created" in result.stderr
    mock_svc.hec_tokens.create.assert_called_once()
    _, kwargs = mock_svc.hec_tokens.create.call_args
    assert kwargs["index"] == "main"


def test_delete_dry_run() -> None:
    result = CliRunner().invoke(cli, ["hec", "delete", "my_token"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.hec.get_client")
def test_delete_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    token = _mock_token()
    mock_svc.hec_tokens.__getitem__.return_value = token
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "hec", "delete", "my_token"])
    assert result.exit_code == 0
    assert "deleted" in result.stderr
    token.delete.assert_called_once()


def test_enable_dry_run() -> None:
    result = CliRunner().invoke(cli, ["hec", "enable", "my_token"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.hec.get_client")
def test_enable_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    token = _mock_token()
    mock_svc.hec_tokens.__getitem__.return_value = token
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "hec", "enable", "my_token"])
    assert result.exit_code == 0
    assert "enabled" in result.stderr
    token.enable.assert_called_once()


def test_disable_dry_run() -> None:
    result = CliRunner().invoke(cli, ["hec", "disable", "my_token"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.hec.get_client")
def test_disable_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    token = _mock_token()
    mock_svc.hec_tokens.__getitem__.return_value = token
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "hec", "disable", "my_token"])
    assert result.exit_code == 0
    assert "disabled" in result.stderr
    token.disable.assert_called_once()


@patch(_PATCH)
def test_create_with_set(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "hec",
            "create",
            "--name",
            "ack_token",
            "--set",
            "useACK=1",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = mock_svc.hec_tokens.create.call_args
    assert kwargs["useACK"] == "1"


@patch(_PATCH)
def test_settings_get(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(
        {
            "entry": [
                {
                    "content": {
                        "disabled": "0",
                        "port": "8088",
                        "enableSSL": "1",
                        "dedicatedIoThreads": "0",
                    }
                }
            ]
        }
    ).encode()
    svc.get.return_value = resp

    result = CliRunner().invoke(cli, ["--json", "hec", "settings"])
    assert result.exit_code == 0
    assert "8088" in result.output


@patch(_PATCH)
def test_settings_enable(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(cli, ["--yes", "hec", "settings", "--enable"])
    assert result.exit_code == 0
    svc.post.assert_called_once()
    call_kwargs = svc.post.call_args
    assert call_kwargs.kwargs["disabled"] == "0"


@patch("splunkctl.commands.hec.req.post")
@patch(_PATCH)
def test_send_posts_event(mock_gc: MagicMock, mock_post: MagicMock) -> None:
    svc = mock_gc.return_value.service
    token = _mock_token()
    svc.hec_tokens.__getitem__.return_value = token
    svc.host = "localhost"
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(
        {"entry": [{"content": {"port": "8088", "enableSSL": "0"}}]}
    ).encode()
    svc.get.return_value = resp
    mock_post.return_value.raise_for_status = MagicMock()

    result = CliRunner().invoke(
        cli,
        ["--yes", "hec", "send", "my_token", "test event"],
    )
    assert result.exit_code == 0
    call_args = mock_post.call_args
    assert "http://localhost:8088" in call_args.args[0]
    assert call_args.kwargs["headers"]["Authorization"] == "Splunk abc-123"
