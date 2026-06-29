"""Tests for splunkctl.client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from splunkctl.client import SplunkClient, get_client


def test_client_lazy_no_connect() -> None:
    c = SplunkClient(host="nowhere")
    assert c._service is None


@patch("splunkctl.client.splunk_client.connect")
def test_client_connects_on_service_access(
    mock_connect: MagicMock, tmp_path: Path
) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("host: testhost\nport: 8089\nusername: u\npassword: p\n")
    c = SplunkClient(config_path=cfg_path)
    _ = c.service
    mock_connect.assert_called_once()
    call_kwargs = mock_connect.call_args[1]
    assert call_kwargs["host"] == "testhost"
    assert call_kwargs["username"] == "u"


@patch("splunkctl.client.splunk_client.connect")
def test_client_token_auth(mock_connect: MagicMock, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("host: h\ntoken: mytoken\n")
    c = SplunkClient(config_path=cfg_path)
    _ = c.service
    call_kwargs = mock_connect.call_args[1]
    assert call_kwargs["splunkToken"] == "mytoken"
    assert "username" not in call_kwargs


def test_get_client_from_context() -> None:
    @click.command()
    @click.pass_context
    def dummy(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj["config"] = None
        ctx.obj["timeout"] = 30
        ctx.obj["debug"] = False
        c = get_client(ctx)
        assert isinstance(c, SplunkClient)
        assert c._service is None

    runner = CliRunner()
    result = runner.invoke(dummy)
    assert result.exit_code == 0
