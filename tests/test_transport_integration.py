"""Clients install policy transports before any authentication."""

# ruff: noqa: S106

from unittest.mock import MagicMock, patch

import pytest

from splunkctl.auth import broker
from splunkctl.client import SplunkClient


def test_sdk_policy_installed_before_connect(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "current: test\nprofiles:\n  test:\n"
        "    host: example.test\n    token: placeholder\n"
    )
    with patch("splunkctl.client.splunk_client.connect") as connect:
        _ = SplunkClient(config_path=config).service
    assert callable(connect.call_args.kwargs["handler"])


def test_browser_login_refused_before_browser_probe():
    from splunkctl.request_context import invocation
    from splunkctl.request_policy import ReadOnlyError

    with (
        invocation("auth login", True),
        patch.object(broker, "browser_available") as probe,
    ):
        with pytest.raises(ReadOnlyError, match="read-only:"):
            broker.run_login(
                login_url="https://example.test/login",
                expected_origin="https://example.test",
                verify=True,
                timeout=1,
            )
    probe.assert_not_called()


def test_soar_web_login_refused_before_any_request():
    from splunkctl.request_context import invocation
    from splunkctl.request_policy import ReadOnlyError
    from splunkctl.soar.client import SOARClient
    from splunkctl.soar.web import ensure_web_login

    client = SOARClient(host="example.test", username="u", password="placeholder")
    with (
        invocation("soar playbooks delete", True),
        patch("splunkctl.soar.web.PolicySession", return_value=MagicMock()) as session,
    ):
        with pytest.raises(ReadOnlyError, match="read-only:"):
            ensure_web_login(client)
    session.assert_not_called()


def test_user_agent_on_all_client_transports(tmp_path):
    import io
    import json

    import requests

    from splunkctl import __version__
    from splunkctl.request_context import invocation
    from splunkctl.soar.client import SOARClient
    from splunkctl.soar.web import ensure_web_login
    from splunkctl.web_session import _WebSession

    dispatched = []

    def send(_adapter, request, **_kwargs):
        dispatched.append(request.headers["User-Agent"])
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.request = request
        return response

    def sdk_send(url, message, **kwargs):
        dispatched.append(dict(message["headers"])["User-Agent"])
        return {
            "status": 200,
            "headers": [],
            "body": io.BytesIO(json.dumps({}).encode()),
        }

    def connect(**kwargs):
        kwargs["handler"](
            "https://example.test:8089/services/server/info",
            {"method": "GET", "headers": []},
        )
        return MagicMock()

    config = tmp_path / "config.yaml"
    config.write_text(
        "current: test\nprofiles:\n  test:\n"
        "    host: example.test\n    token: placeholder\n"
    )
    service = MagicMock(host="example.test", username="u", password="placeholder")
    service.confs["web"]["settings"].__getitem__.return_value = "8000"
    service.confs["web"]["settings"].content.get.return_value = "0"
    with (
        invocation("info", False) as context,
        patch("requests.adapters.HTTPAdapter.send", send),
        patch("splunkctl.client.handler", return_value=sdk_send),
        patch("splunkctl.client.splunk_client.connect", side_effect=connect),
    ):
        _ = SplunkClient(config_path=config).service
        _WebSession(service)._request("GET", "http://example.test:8000/en-US/")
        soar = SOARClient(
            host="example.test",
            token="placeholder",
            cookies={"sessionid": "s", "csrftoken": "c"},
        )
        soar.get("version")
        ensure_web_login(soar).get("https://example.test:8443/")
        expected = f"splunkctl/{__version__} (cmd=info; requestID={context.request_id})"
    assert dispatched == [expected] * 4


def test_readonly_missing_browser_session_never_reauthenticates(tmp_path):
    from splunkctl import config as cfg_mod
    from splunkctl.errors import WebSessionError
    from splunkctl.request_context import invocation

    config = tmp_path / "config.yaml"
    cfg_mod.save(
        {
            "host": "example.test",
            "auth_mode": "browser",
            "web_url": "https://example.test:8000",
        },
        config,
    )
    with (
        invocation("info", True),
        patch("splunkctl.auth.session.load", return_value=None),
        patch("splunkctl.auth.detector.probe") as probe,
        patch("splunkctl.client.splunk_client.connect") as connect,
    ):
        with pytest.raises(WebSessionError, match="existing session"):
            _ = SplunkClient(config_path=config).service
    probe.assert_not_called()
    connect.assert_not_called()
