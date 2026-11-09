"""Headed-Chromium SAML login via Playwright (lazy import).

Playwright and its Chromium build are optional and only imported here. The
browser context is temporary and isolated: identity-provider cookies are
discarded when the context closes, and only the final product-origin cookies
are returned.
"""

from __future__ import annotations

import importlib
import time
from typing import Any
from urllib.parse import urlsplit

from splunkctl.request_context import readonly
from splunkctl.request_policy import ReadOnlyError


class BrokerError(RuntimeError):
    """A browser-login failure with an ``errors.py``-compatible kind."""

    def __init__(self, message: str, *, kind: str = "auth") -> None:  # noqa: D107
        super().__init__(message)
        self.message = message
        self.kind = kind


def _sync_playwright() -> Any:
    """Import the sync Playwright API lazily; raises ImportError when absent."""
    return importlib.import_module("playwright.sync_api").sync_playwright()


def browser_available() -> bool:
    """True when the Playwright package imports."""
    try:
        _sync_playwright()
        return True
    except ImportError:
        return False


def install_hint() -> str:
    """The exact optional install commands, shown when the browser is missing."""
    return (
        "Install the optional browser support with: "
        "pip install 'splunkctl[browser]' && python -m playwright install chromium"
    )


def _origin_of(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    port = parts.port
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    return parts.scheme, parts.hostname or "", port


def run_login(
    *,
    login_url: str,
    expected_origin: str,
    verify: bool,
    timeout: int,
) -> dict[str, str]:
    """Open headed Chromium, follow SAML to ``expected_origin``, return cookies.

    Raises :class:`BrokerError` on timeout, wrong final origin, or early close.
    """
    if readonly():
        raise ReadOnlyError("read-only: browser login is refused")
    if not browser_available():
        raise BrokerError(
            "Playwright or Chromium is not installed. " + install_hint(),
            kind="usage",
        )
    with _sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=not verify)
        page = context.new_page()
        deadline = time.monotonic() + timeout
        expected = _origin_of(expected_origin)
        left_origin = False

        def _departed(url: str) -> bool:
            # Only an http(s) page on another origin is the IdP; error pages
            # (chrome-error://) and about:blank are not.
            return urlsplit(url).scheme in ("http", "https") and (
                _origin_of(url) != expected
            )

        def _on_navigated(frame: Any) -> None:
            nonlocal left_origin
            if frame == page.main_frame and _departed(frame.url):
                left_origin = True

        try:
            # A fast IdP (silent SSO, or the lab's auto-filled form) can return
            # to the product between two polls of page.url (measured at
            # 0.24-0.66 s on the Keycloak lab), so record every main-frame
            # navigation instead of only sampling the current URL.
            page.on("framenavigated", _on_navigated)
            page.goto(login_url)
            # The login route is often on the product origin and only bounces to
            # the IdP after a JS auto-submit or server redirect. Wait for the
            # browser to leave the product origin first, then wait for it to
            # return once the user completes the identity-provider flow.
            while not left_origin and not _departed(page.url):
                if page.is_closed():
                    raise BrokerError(
                        "The browser was closed before login finished.", kind="auth"
                    )
                if time.monotonic() > deadline:
                    raise BrokerError(
                        f"Timed out waiting for the identity provider to take over "
                        f"from {login_url}.",
                        kind="timeout",
                    )
                page.wait_for_timeout(500)
            while _origin_of(page.url) != expected:
                if page.is_closed():
                    raise BrokerError(
                        "The browser was closed before login finished.", kind="auth"
                    )
                if time.monotonic() > deadline:
                    raise BrokerError(
                        f"Timed out waiting for login to reach the expected origin "
                        f"({expected_origin}).",
                        kind="timeout",
                    )
                page.wait_for_timeout(500)
            cookies = {}
            for cookie in context.cookies(urls=[expected_origin]):
                if cookie.get("name") and cookie.get("value"):
                    cookies[cookie["name"]] = cookie["value"]
            return cookies
        finally:
            context.close()
            browser.close()
