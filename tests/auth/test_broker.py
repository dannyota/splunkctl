"""Tests for the Playwright browser broker (no real browser launched)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from splunkctl.auth import broker


@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_returns_cookies_on_origin(mock_sp: MagicMock) -> None:
    page = MagicMock()
    # The login route stays on the product origin, then bounces to the IdP,
    # then returns to the product once the user finishes the IdP flow.
    type(page).url = PropertyMock(
        side_effect=[
            "http://siem:8000/en-US/account/login",  # still on the login page
            "http://idp:8080/realms/x/login",  # bounced to the IdP
            "http://idp:8080/realms/x/login",  # still on the IdP
            "http://siem:8000/app/launcher",  # back on the product
        ]
    )
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


@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_catches_idp_round_trip_between_polls(mock_sp: MagicMock) -> None:
    """A fast IdP returns before the first poll; the navigation event counts."""
    page = MagicMock()
    page.url = "http://siem:8000/en-US/app/launcher/home"  # every poll: product
    page.is_closed.return_value = False
    handlers = {}
    page.on.side_effect = lambda event, handler: handlers.__setitem__(event, handler)

    def goto(_url: str) -> None:
        idp_frame = page.main_frame
        idp_frame.url = "http://idp:8080/realms/x/protocol/saml"
        handlers["framenavigated"](idp_frame)

    page.goto.side_effect = goto
    context = MagicMock()
    context.cookies.return_value = [{"name": "splunkd_8000", "value": "KEY"}]
    context.new_page.return_value = page
    browser = mock_sp.return_value.__enter__.return_value.chromium.launch.return_value
    browser.new_context.return_value = context

    result = broker.run_login(
        login_url="http://siem:8000/en-US/account/login",
        expected_origin="http://siem:8000",
        verify=True,
        timeout=60,
    )
    assert result == {"splunkd_8000": "KEY"}
    page.wait_for_timeout.assert_not_called()


_LOGIN = "http://siem:8000/en-US/account/login"
_HOME = "http://siem:8000/en-US/app/launcher/home"
_IDP = "http://idp:8080/realms/x/protocol/saml"


def _live_page() -> tuple[MagicMock, Callable[..., None]]:
    """A page whose url follows navigate(); framenavigated handlers are kept."""
    page = MagicMock()
    page.is_closed.return_value = False
    state = {"url": "about:blank"}
    type(page).url = PropertyMock(side_effect=lambda: state["url"])
    handlers: dict[str, Callable[[MagicMock], None]] = {}
    page.on.side_effect = lambda event, handler: handlers.__setitem__(event, handler)

    def navigate(url: str, frame: MagicMock | None = None) -> None:
        if frame is None:  # main frame: page.url and main_frame.url agree
            state["url"] = url
            frame = page.main_frame
        frame.url = url
        handlers["framenavigated"](frame)

    return page, navigate


def _login_with(mock_sp: MagicMock, page: MagicMock) -> dict[str, str]:
    context = MagicMock()
    context.cookies.return_value = [{"name": "splunkd_8000", "value": "KEY"}]
    context.new_page.return_value = page
    browser = mock_sp.return_value.__enter__.return_value.chromium.launch.return_value
    browser.new_context.return_value = context
    return broker.run_login(
        login_url=_LOGIN, expected_origin="http://siem:8000", verify=True, timeout=60
    )


@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_round_trip_inside_first_poll(mock_sp: MagicMock) -> None:
    """goto lands on the product; the whole IdP visit happens in one poll."""
    page, navigate = _live_page()
    page.goto.side_effect = navigate

    def poll(_ms: int) -> None:
        navigate(_IDP)
        navigate(_HOME)

    page.wait_for_timeout.side_effect = poll
    assert _login_with(mock_sp, page) == {"splunkd_8000": "KEY"}
    page.wait_for_timeout.assert_called_once()


@pytest.mark.parametrize("blank", ["chrome-error://chromewebdata/", "about:blank"])
@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_waits_for_idp_after_non_http_page(
    mock_sp: MagicMock, blank: str
) -> None:
    """Error or blank page, then the product login: still wait for the IdP."""
    page, navigate = _live_page()

    def goto(url: str) -> None:
        navigate(blank)
        navigate(url)

    page.goto.side_effect = goto
    steps = iter([lambda: None, lambda: navigate(_IDP), lambda: navigate(_HOME)])
    page.wait_for_timeout.side_effect = lambda _ms: next(steps)()
    assert _login_with(mock_sp, page) == {"splunkd_8000": "KEY"}
    assert page.wait_for_timeout.call_count == 3


@pytest.mark.parametrize(
    "departure",
    [
        pytest.param({"url": _IDP, "frame": MagicMock()}, id="subframe-off-origin"),
        pytest.param({"url": "chrome-error://chromewebdata/"}, id="non-http"),
    ],
)
@patch("splunkctl.auth.broker.time.monotonic", side_effect=[0.0, 1000.0])
@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_navigation_that_is_not_a_departure(
    mock_sp: MagicMock, mock_monotonic: MagicMock, departure: dict[str, Any]
) -> None:
    page, navigate = _live_page()

    def goto(url: str) -> None:
        navigate(url)
        navigate(**departure)

    page.goto.side_effect = goto
    with pytest.raises(broker.BrokerError) as exc:
        _login_with(mock_sp, page)
    assert "identity provider" in exc.value.message


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


@patch("splunkctl.auth.broker.time.monotonic", side_effect=[0.0, 1000.0])
@patch("splunkctl.auth.broker._sync_playwright")
def test_run_login_times_out_when_login_page_stays_on_origin(
    mock_sp: MagicMock, mock_monotonic: MagicMock
) -> None:
    page = MagicMock()
    page.url = "http://siem:8000/en-US/account/login"  # never leaves the product
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
    assert "identity provider" in exc.value.message


@patch("splunkctl.auth.broker.importlib.import_module", side_effect=ImportError)
def test_browser_available_false_when_missing(mock_import: MagicMock) -> None:
    assert broker.browser_available() is False


def test_install_hint_names_package_and_browser() -> None:
    hint = broker.install_hint()
    assert "splunkctl[browser]" in hint
    assert "playwright install chromium" in hint
