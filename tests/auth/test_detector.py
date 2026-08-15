"""Tests for login-flow classification."""

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
