"""Tests for login-flow classification."""

from unittest.mock import MagicMock, patch

import requests

from splunkctl.auth import detector


def test_redirect_to_external_host_is_browser() -> None:
    mode = detector.classify(
        login_url="http://siem:8000/en-US/account/login",
        status=302,
        headers={"Location": "https://idp.example.com/auth"},
        body="",
    )
    assert mode == "browser"


def test_redirect_to_same_host_is_password() -> None:
    mode = detector.classify(
        login_url="http://siem:8000/en-US/account/login",
        status=302,
        headers={"Location": "http://siem:8000/en-US/account/login"},
        body="",
    )
    assert mode == "password"


def test_relative_redirect_is_password() -> None:
    mode = detector.classify(
        login_url="http://siem:8000/en-US/account/login",
        status=302,
        headers={"Location": "/en-US/account/login"},
        body="",
    )
    assert mode == "password"


def test_same_host_scheme_change_is_password() -> None:
    mode = detector.classify(
        login_url="http://siem:8000/en-US/account/login",
        status=302,
        headers={"Location": "https://siem:8000/en-US/account/login"},
        body="",
    )
    assert mode == "password"


def test_http_401_is_password_not_mfa() -> None:
    mode = detector.classify(
        login_url="http://siem:8000/en-US/account/login",
        status=401,
        headers={},
        body="unauthorized",
    )
    assert mode == "password"


def test_login_form_is_password() -> None:
    body = (
        '<form action="/login"><input type="text" name="username">'
        '<input type="password" name="password"></form>'
    )
    mode = detector.classify(
        login_url="http://siem:8000/login", status=200, headers={}, body=body
    )
    assert mode == "password"


def test_saml_marker_is_browser() -> None:
    body = "<html><title>Sign in with SSO</title><p>Single sign-on</p></html>"
    mode = detector.classify(
        login_url="http://siem:8000/login", status=200, headers={}, body=body
    )
    assert mode == "browser"


def test_unknown_when_nothing_matches() -> None:
    mode = detector.classify(
        login_url="http://x", status=200, headers={}, body="<html></html>"
    )
    assert mode == "unknown"


def test_login_url_helpers() -> None:
    assert (
        detector.siem_login_url("https://siem:8000")
        == "https://siem:8000/en-US/account/login"
    )
    assert detector.soar_login_url("https://soar:8443") == "https://soar:8443/login"


@patch("splunkctl.auth.detector.requests.get")
def test_siem_idp_issuer_from_form_action(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(
        status_code=200,
        headers={},
        text=(
            '<form method="post" '
            'action="http://idp:8080/realms/splunklab/protocol/saml">'
        ),
    )
    issuer = detector.siem_idp_issuer("http://siem:8000", verify=True, timeout=30)
    assert issuer == "http://idp:8080/realms/splunklab"


@patch("splunkctl.auth.detector.requests.get")
def test_siem_idp_issuer_from_redirect(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(
        status_code=302,
        headers={"Location": "http://idp:8080/realms/splunklab/protocol/saml"},
        text="",
    )
    issuer = detector.siem_idp_issuer("http://siem:8000", verify=True, timeout=30)
    assert issuer == "http://idp:8080/realms/splunklab"


@patch("splunkctl.auth.detector.requests.get")
def test_siem_idp_issuer_none_when_not_saml(mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(
        status_code=200, headers={}, text='<form action="/local/login">'
    )
    assert detector.siem_idp_issuer("http://siem:8000", verify=True, timeout=30) is None


@patch("splunkctl.auth.detector.requests.get", side_effect=requests.RequestException)
def test_siem_idp_issuer_none_on_error(mock_get: MagicMock) -> None:
    assert detector.siem_idp_issuer("http://siem:8000", verify=True, timeout=30) is None
