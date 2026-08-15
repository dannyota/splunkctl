"""Tests for the Playwright browser broker (no real browser launched)."""

from unittest.mock import MagicMock, patch

import pytest

from splunkctl.auth import broker


@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_returns_cookies_on_origin(mock_sp: MagicMock) -> None:
    page = MagicMock()
    page.url = "http://siem:8000/en-US/account/login"
    page.is_closed.return_value = False
    context = MagicMock()
    cookies = [
        {"name": "splunkd_8000", "value": "SESSIONKEY"},
        {"name": "splunkweb_csrf_token", "value": "x"},
    ]
    context.cookies.return_value = cookies
    context.new_page.return_value = page
    browser = mock_sp.return_value.__enter__.return_value.chromium.launch.return_value
    browser.new_context.return_value = context

    result = broker.run_login(
        login_url="http://siem:8000/en-US/account/login",
        expected_origin="http://siem:8000",
        verify=True,
        timeout=60,
    )
    assert result == {"splunkd_8000": "SESSIONKEY", "splunkweb_csrf_token": "x"}
    page.goto.assert_called_once()
    context.cookies.assert_called_once_with(urls=["http://siem:8000"])
    context.close.assert_called_once()


@patch("splunkctl.auth.broker.time.monotonic", side_effect=[0.0, 1000.0])
@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_wrong_origin_raises(
    mock_sp: MagicMock, mock_monotonic: MagicMock
) -> None:
    page = MagicMock()
    page.url = "https://evil.example.com/phish"
    page.is_closed.return_value = False
    context = MagicMock()
    context.new_page.return_value = page
    browser = mock_sp.return_value.__enter__.return_value.chromium.launch.return_value
    browser.new_context.return_value = context

    with pytest.raises(broker.BrokerError) as exc:
        broker.run_login(
            login_url="http://siem:8000/en-US/account/login",
            expected_origin="http://siem:8000",
            verify=True,
            timeout=60,
        )
    assert "expected origin" in exc.value.message
    assert "evil.example.com" not in exc.value.message


@patch("splunkctl.auth.broker.importlib.import_module", side_effect=ImportError)
def test_browser_available_false_when_missing(mock_import: MagicMock) -> None:
    assert broker.browser_available() is False


def test_install_hint_names_package_and_browser() -> None:
    hint = broker.install_hint()
    assert "splunkctl[browser]" in hint
    assert "playwright install chromium" in hint
