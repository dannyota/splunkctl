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


def _mock_service() -> MagicMock:
    svc = MagicMock()
    svc.host = "testhost"
    svc.username = "u"
    svc.password = "p"
    settings = MagicMock()
    settings.__getitem__.side_effect = lambda k: {"httpport": "8000"}[k]
    settings.content.get.return_value = "0"
    svc.confs.__getitem__.return_value.__getitem__.return_value = settings
    return svc


def _resp(*, text: str = "", json_body: object = None, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.status_code = status
    if json_body is None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = json_body
    return r


def _csrf_cookie() -> MagicMock:
    cookie = MagicMock()
    cookie.name = "splunkweb_csrf_token_8000"
    cookie.value = "tok123"
    return cookie


@patch("splunkctl.client.requests.Session")
def test_websession_login_extracts_csrf(mock_session_cls: MagicMock) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "good"}),
    ]
    session.cookies = [_csrf_cookie()]

    ws = _WebSession(_mock_service(), verify=False)
    ws._login()
    assert ws._csrf_token == "tok123"
    # login POST carried the cval extracted from the login page
    post_call = session.request.call_args_list[1]
    assert post_call.args[0] == "POST"
    assert post_call.kwargs["data"]["cval"] == "42"


@patch("splunkctl.client.requests.Session")
def test_upload_lookup_posts_form_fields(
    mock_session_cls: MagicMock, tmp_path: Path
) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "good"}),
        _resp(json_body={"status": "OK"}),
    ]
    session.cookies = [_csrf_cookie()]

    csv = tmp_path / "x.csv"
    csv.write_text("a,b\n1,2\n")
    ws = _WebSession(_mock_service(), verify=False)
    ws.upload_lookup("x.csv", csv, app="search")

    upload_call = session.request.call_args_list[2]
    method, url = upload_call.args[0], upload_call.args[1]
    assert method == "POST"
    assert url.endswith("/manager/search/data/lookup-table-files/_new")
    data = upload_call.kwargs["data"]
    assert data["splunk_form_key"] == "tok123"
    assert data["name"] == "x.csv"
    assert "spl-ctrl_lookupfile" in upload_call.kwargs["files"]


@patch("splunkctl.client.requests.Session")
def test_upload_lookup_error_raises(
    mock_session_cls: MagicMock, tmp_path: Path
) -> None:
    import pytest

    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "good"}),
        _resp(json_body={"status": "ERROR", "msg": "already exists"}),
    ]
    session.cookies = [_csrf_cookie()]

    csv = tmp_path / "x.csv"
    csv.write_text("a,b\n")
    ws = _WebSession(_mock_service(), verify=False)
    with pytest.raises(RuntimeError, match="already exists"):
        ws.upload_lookup("x.csv", csv, app="search")


@patch("splunkctl.client.requests.Session")
def test_install_app_posts_state(mock_session_cls: MagicMock, tmp_path: Path) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "good"}),
        _resp(text='<input name="state" type="hidden" value="abc123"/>'),
        _resp(text="ok", status=200),
    ]
    session.cookies = [_csrf_cookie()]

    pkg = tmp_path / "app.tar.gz"
    pkg.write_bytes(b"fake")
    ws = _WebSession(_mock_service(), verify=False)
    ws.install_app(pkg)

    post_call = session.request.call_args_list[3]
    assert post_call.args[0] == "POST"
    assert post_call.args[1].endswith("/manager/appinstall/_upload")
    assert post_call.kwargs["data"]["state"] == "abc123"
    assert "appfile" in post_call.kwargs["files"]


def test_set_acl_defaults_owner_from_entity() -> None:
    entity = MagicMock()
    entity.access = {"owner": "alice", "sharing": "user"}
    c = SplunkClient(host="h")
    c.set_acl(entity, sharing="app")
    entity.acl_update.assert_called_once_with(sharing="app", owner="alice")


def test_set_acl_explicit_owner() -> None:
    entity = MagicMock()
    entity.access = {}
    c = SplunkClient(host="h")
    c.set_acl(entity, sharing="global", owner="nobody")
    entity.acl_update.assert_called_once_with(sharing="global", owner="nobody")
