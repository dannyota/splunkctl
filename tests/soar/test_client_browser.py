"""Tests for SOAR client browser-session integration."""

from unittest.mock import MagicMock, patch

from splunkctl.soar.client import SOARClient


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {}
    return resp


@patch("splunkctl.soar.client.requests.Session.request")
def test_cookies_are_sent_on_get(mock_request: MagicMock) -> None:
    mock_request.return_value = _ok_response()
    client = SOARClient(host="soar", cookies={"sessionid": "SID", "csrftoken": "CSRF"})
    client.get("version")
    _, kwargs = mock_request.call_args
    assert kwargs["cookies"] == {"sessionid": "SID", "csrftoken": "CSRF"}


@patch("splunkctl.soar.client.requests.Session.request")
def test_csrf_header_on_post(mock_request: MagicMock) -> None:
    mock_request.return_value = _ok_response()
    client = SOARClient(host="soar", cookies={"sessionid": "SID", "csrftoken": "CSRF"})
    client.post("container", body={"name": "x"})
    _, kwargs = mock_request.call_args
    assert kwargs["headers"]["X-CSRFToken"] == "CSRF"
    assert kwargs["cookies"] == {"sessionid": "SID", "csrftoken": "CSRF"}


def test_ensure_web_login_reuses_browser_cookies() -> None:
    from splunkctl.soar import web

    client = SOARClient(host="soar", cookies={"sessionid": "SID", "csrftoken": "CSRF"})
    sess = web.ensure_web_login(client)
    assert sess.cookies.get("sessionid") == "SID"
    assert client._web_csrf == "CSRF"
