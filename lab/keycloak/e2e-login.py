#!/usr/bin/env python3
"""Lab-only end-to-end harness for ``splunkctl auth login`` against Keycloak.

The real splunkctl broker still drives Chromium: it opens the product login
route, waits for the identity provider to take over and for the browser to
return to the product origin, extracts and validates the session, and saves it.
This harness only fills the Keycloak username and password form.

Usage, from the repository root, with the lab profile file::

    export TEST_USER_PASSWORD=...   # from lab/keycloak/.env; never print it
    python lab/keycloak/e2e-login.py --config lab.yaml auth login --target siem

Environment:
    TEST_USER            Keycloak user (default: samluser).
    TEST_USER_PASSWORD   Keycloak password (required).
    KEYCLOAK_HOST/PORT   Keycloak origin (default: 100.65.1.1:8080).
    E2E_HEADLESS=1       Launch Chromium headless instead of headed.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from splunkctl.auth import broker
from splunkctl.main import cli

# Fills the Keycloak form once per page load, at most twice per tab, so a
# rejected password cannot loop into repeated failed logins.
_FILL_JS = """
(() => {
  const cfg = %s;
  if (location.origin !== cfg.origin) return;
  document.addEventListener("DOMContentLoaded", () => {
    const user = document.querySelector("#username");
    const pass = document.querySelector("#password");
    const submit = document.querySelector("#kc-login");
    if (!user || !pass || !submit) return;
    const tries = Number(sessionStorage.getItem("e2e-login-tries") || "0");
    if (tries >= 2) return;
    sessionStorage.setItem("e2e-login-tries", String(tries + 1));
    for (const [el, value] of [[user, cfg.user], [pass, cfg.password]]) {
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    submit.click();
  });
})();
"""


class _Proxy:
    """Delegate every attribute to the wrapped Playwright object."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _Browser(_Proxy):
    def __init__(self, inner: Any, script: str) -> None:
        super().__init__(inner)
        self._script = script

    def new_context(self, **kwargs: Any) -> Any:
        context = self._inner.new_context(**kwargs)
        context.add_init_script(self._script)
        return context


class _Chromium(_Proxy):
    def __init__(self, inner: Any, script: str) -> None:
        super().__init__(inner)
        self._script = script

    def launch(self, **kwargs: Any) -> _Browser:
        if os.environ.get("E2E_HEADLESS") == "1":
            kwargs["headless"] = True
        return _Browser(self._inner.launch(**kwargs), self._script)


class _Playwright(_Proxy):
    def __init__(self, inner: Any, script: str) -> None:
        super().__init__(inner)
        self.chromium = _Chromium(inner.chromium, script)


class _Manager:
    """Context manager matching ``sync_playwright()`` that yields the proxy."""

    def __init__(self, inner: Any, script: str) -> None:
        self._inner = inner
        self._script = script

    def __enter__(self) -> _Playwright:
        return _Playwright(self._inner.__enter__(), self._script)

    def __exit__(self, *exc: object) -> Any:
        return self._inner.__exit__(*exc)


def _fill_script() -> str:
    password = os.environ.get("TEST_USER_PASSWORD")
    if not password:
        raise SystemExit("TEST_USER_PASSWORD is not set (see lab/keycloak/.env)")
    host = os.environ.get("KEYCLOAK_HOST", "100.65.1.1")
    port = os.environ.get("KEYCLOAK_PORT", "8080")
    cfg = {
        "origin": f"http://{host}:{port}",
        "user": os.environ.get("TEST_USER", "samluser"),
        "password": password,
    }
    return _FILL_JS % json.dumps(cfg)


def main() -> int:
    """Patch the broker's Playwright entry point, then run the splunkctl CLI."""
    script = _fill_script()
    real = broker._sync_playwright
    broker._sync_playwright = lambda: _Manager(real(), script)
    try:
        rv = cli.main(args=sys.argv[1:], prog_name="splunkctl", standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.exceptions.Abort:
        return 1
    return rv if isinstance(rv, int) else 0


if __name__ == "__main__":
    sys.exit(main())
