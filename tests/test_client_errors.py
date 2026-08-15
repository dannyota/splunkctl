"""WebSessionError classification and TLS-off warning tests."""

import json
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

import splunkctl.client as client_mod
from splunkctl.auth.session import SessionError
from splunkctl.client import SplunkClient
from splunkctl.errors import WebSessionError, classify
from splunkctl.main import _CLI

# --- WebSessionError classification ---


def test_websession_error_classified_as_auth() -> None:
    exc = WebSessionError("Splunk Web login failed: bad creds", kind="auth")
    result = classify(exc)
    assert result is not None
    assert result.kind == "auth"
    assert result.message == "Splunk Web login failed: bad creds"
    assert result.http_status is None


def test_websession_error_classified_as_web() -> None:
    exc = WebSessionError("Could not obtain CSRF token", kind="web")
    result = classify(exc)
    assert result is not None
    assert result.kind == "web"
    assert result.message == "Could not obtain CSRF token"


def test_websession_error_is_runtimeerror_subclass() -> None:
    """Ensure backward compat: code catching RuntimeError still works."""
    exc = WebSessionError("test")
    assert isinstance(exc, RuntimeError)


# --- End-to-end: WebSessionError -> JSON error envelope ---


def _cli_raising(exc: Exception) -> click.Group:
    @click.group(cls=_CLI)
    @click.option("--json", "use_json", is_flag=True)
    @click.option("--format", "fmt", default=None)
    @click.pass_context
    def grp(ctx: click.Context, use_json: bool, fmt: str | None) -> None:
        ctx.ensure_object(dict)
        ctx.obj["json"] = use_json
        ctx.obj["format"] = fmt

    @grp.command()
    def boom() -> None:
        raise exc

    return grp


def test_websession_auth_error_produces_json_envelope() -> None:
    exc = WebSessionError("Splunk Web login failed: bad password", kind="auth")
    result = CliRunner().invoke(_cli_raising(exc), ["--json", "boom"])
    assert result.exit_code == 1
    envelope = json.loads(result.stderr)["error"]
    assert envelope["kind"] == "auth"
    assert "bad password" in envelope["message"]
    assert envelope["http_status"] is None


def test_websession_web_error_produces_json_envelope() -> None:
    exc = WebSessionError("Lookup upload failed: HTTP 500", kind="web")
    result = CliRunner().invoke(_cli_raising(exc), ["--json", "boom"])
    assert result.exit_code == 1
    envelope = json.loads(result.stderr)["error"]
    assert envelope["kind"] == "web"
    assert "HTTP 500" in envelope["message"]


# --- _WebSession raises WebSessionError (not bare RuntimeError) ---


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
def test_login_bad_creds_raises_websession_error(
    mock_session_cls: MagicMock,
) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "fail", "msg": "Invalid credentials"}),
    ]
    session.cookies = []

    ws = _WebSession(_mock_service(), verify=False)
    with pytest.raises(WebSessionError, match="Invalid credentials"):
        ws._login()


@patch("splunkctl.client.requests.Session")
def test_login_non_json_response_raises_websession_error(
    mock_session_cls: MagicMock,
) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(text="<html>502 Bad Gateway</html>", status=502),
    ]
    session.cookies = []

    ws = _WebSession(_mock_service(), verify=False)
    with pytest.raises(WebSessionError, match="HTTP 502"):
        ws._login()


@patch("splunkctl.client.requests.Session")
def test_missing_csrf_raises_websession_error(
    mock_session_cls: MagicMock,
) -> None:
    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "ok"}),
    ]
    session.cookies = []  # no CSRF cookie

    ws = _WebSession(_mock_service(), verify=False)
    with pytest.raises(WebSessionError, match="CSRF"):
        ws._login()


def test_token_only_auth_raises_websession_error() -> None:
    from splunkctl.client import _WebSession

    svc = _mock_service()
    svc.username = ""
    svc.password = ""
    with pytest.raises(WebSessionError, match="username/password"):
        _WebSession(svc, verify=False)


@patch("splunkctl.client.requests.Session")
def test_app_install_http_error_raises_websession_error(
    mock_session_cls: MagicMock, tmp_path: object
) -> None:
    from pathlib import Path

    from splunkctl.client import _WebSession

    session = mock_session_cls.return_value
    session.request.side_effect = [
        _resp(text='{"cval": 42}'),
        _resp(json_body={"status": "ok"}),
        _resp(text='<input name="state" type="hidden" value="s1"/>'),
        _resp(text="error", status=403),
    ]
    session.cookies = [_csrf_cookie()]

    pkg = Path(str(tmp_path)) / "app.tar.gz"
    pkg.write_bytes(b"fake")

    ws = _WebSession(_mock_service(), verify=False)
    with pytest.raises(WebSessionError, match="HTTP 403"):
        ws.install_app(pkg)


# --- TLS-off warning (S2 runtime half for SIEM client) ---


@patch("splunkctl.client.splunk_client.connect")
def test_tls_off_warning_emitted_once(
    mock_connect: MagicMock, tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """verify=false prints one warning to stderr, not repeated on second connect."""
    from pathlib import Path

    # Reset module-level flag so this test is isolated.
    client_mod._tls_warned = False

    cfg_path = Path(str(tmp_path)) / "config.yaml"
    cfg_path.write_text("host: h\nusername: u\npassword: p\nverify: false\n")

    c1 = SplunkClient(config_path=cfg_path)
    _ = c1.service
    captured = capsys.readouterr()
    assert "TLS certificate verification is disabled" in captured.err

    # Second client in the same process: no repeat.
    c2 = SplunkClient(config_path=cfg_path)
    _ = c2.service
    captured2 = capsys.readouterr()
    assert "TLS" not in captured2.err

    # Reset for other tests.
    client_mod._tls_warned = False


@patch("splunkctl.client.splunk_client.connect")
def test_tls_on_no_warning(
    mock_connect: MagicMock, tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    from pathlib import Path

    client_mod._tls_warned = False

    cfg_path = Path(str(tmp_path)) / "config.yaml"
    cfg_path.write_text("host: h\nusername: u\npassword: p\nverify: true\n")

    c = SplunkClient(config_path=cfg_path)
    _ = c.service
    captured = capsys.readouterr()
    assert "TLS" not in captured.err

    client_mod._tls_warned = False


def test_classify_session_error_carries_kind() -> None:
    classified = classify(SessionError("boom", kind="usage"))
    assert classified is not None
    assert classified.kind == "usage"
    assert classified.message == "boom"
