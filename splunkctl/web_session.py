"""Splunk Web form sessions for lookup and app uploads."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

import click
import requests
import urllib3

from splunkctl.errors import WebSessionError
from splunkctl.request_context import Invocation
from splunkctl.transport import PolicySession


class _WebSession:
    """Authenticated Splunk Web session for form-handler operations.

    Uses ``requests`` deliberately: the manager form handlers answer a
    plain urllib POST with a 303 that dead-ends in a 404, while a
    keep-alive session receives the JSON result directly (verified
    against Splunk 10.4). TLS verification is on unless the user's
    config explicitly disables it for self-signed dev instances.
    """

    def __init__(
        self,
        service: Any,
        *,
        identity: Invocation | None = None,
        verify: bool = True,
        debug: bool = False,
        timeout: int = 30,
        web_url: str | None = None,
    ) -> None:
        self._host: str = service.host
        # A configured web_url wins over the server's httpport: port-mapped
        # containers and proxies serve Splunk Web on a different address.
        self._web_base_override: str | None = web_url.rstrip("/") if web_url else None
        self._username: str = service.username
        self._password: str = service.password
        if not self._username or not self._password:
            raise WebSessionError(
                "Lookup upload requires username/password authentication. "
                "Token-only auth cannot authenticate to Splunk Web UI.",
                kind="auth",
            )

        web_conf = service.confs["web"]["settings"]
        self._web_port = int(web_conf["httpport"])
        self._web_ssl = str(web_conf.content.get("enableSplunkWebSSL", "0")) == "1"

        self._debug = debug
        self._timeout = timeout
        self._session = PolicySession(self._base_url, kind="web", identity=identity)
        self._session.verify = verify
        if not verify:
            # verify=false is an explicit config choice (lab/self-signed);
            # without this every request spams InsecureRequestWarning.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._csrf_token: str | None = None
        self._logged_in = False

    @property
    def _base_url(self) -> str:
        if self._web_base_override:
            return self._web_base_override
        scheme = "https" if self._web_ssl else "http"
        return f"{scheme}://{self._host}:{self._web_port}"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        if self._debug:
            click.echo(f"web {method} {url} -> {resp.status_code}", err=True)
        return resp

    def _login(self) -> None:
        """Authenticate to Splunk Web and obtain session cookies."""
        # loginType=splunk keeps the local login form when SAML is enabled
        # (verified on Splunk 10.6.1.1); Splunk-native auth ignores it.
        login_url = f"{self._base_url}/en-US/account/login?loginType=splunk"
        page = self._request("GET", login_url).text

        m = re.search(r'"cval"\s*:\s*(\d+)', page)
        cval = m.group(1) if m else "0"

        resp = self._request(
            "POST",
            login_url,
            data={
                "username": self._username,
                "password": self._password,
                "cval": cval,
            },
        )
        try:
            body: dict[str, Any] = resp.json()
        except ValueError:
            raise WebSessionError(
                f"Splunk Web login failed: HTTP {resp.status_code}",
                kind="auth",
            ) from None
        if resp.status_code >= 400 or body.get("status") == "fail":
            msg = body.get("msg") or f"HTTP {resp.status_code}"
            raise WebSessionError(f"Splunk Web login failed: {msg}", kind="auth")

        for cookie in self._session.cookies:
            if cookie.name and cookie.name.startswith("splunkweb_csrf_token"):
                self._csrf_token = cookie.value
                break
        if not self._csrf_token:
            raise WebSessionError(
                "Could not obtain CSRF token from Splunk Web", kind="web"
            )
        self._logged_in = True

    def upload_lookup(
        self,
        name: str,
        file_path: Path,
        *,
        app: str = "search",
        update: bool = False,
    ) -> None:
        """Upload a lookup file via multipart form POST."""
        if not self._logged_in:
            self._login()

        if update:
            url = (
                f"{self._base_url}/en-US/manager/{app}"
                f"/data/lookup-table-files/{urllib.parse.quote(name)}"
            )
            action = "edit"
        else:
            url = f"{self._base_url}/en-US/manager/{app}/data/lookup-table-files/_new"
            action = "new"

        data: dict[str, str] = {
            "__action": action,
            "__redirect": "",
            "__ns": app,
            "splunk_form_key": self._csrf_token or "",
        }
        if not update:
            data["name"] = name

        resp = self._request(
            "POST",
            url,
            data=data,
            files={"spl-ctrl_lookupfile": (name, file_path.read_bytes(), "text/csv")},
        )
        _expect_ok(resp, "Lookup upload")

    def install_app(
        self,
        file_path: Path,
        *,
        force: bool = False,
    ) -> None:
        """Install a .spl/.tar.gz app via the Web UI upload handler."""
        if not self._logged_in:
            self._login()

        upload_url = f"{self._base_url}/en-US/manager/appinstall/_upload"
        page = self._request("GET", upload_url).text

        m = re.search(r'name="state"\s+[^>]*value="([^"]*)"', page)
        state = m.group(1) if m else ""

        data: dict[str, str] = {
            "state": state,
            "splunk_form_key": self._csrf_token or "",
        }
        if force:
            data["force"] = "1"

        resp = self._request(
            "POST",
            upload_url,
            data=data,
            files={
                "appfile": (
                    file_path.name,
                    file_path.read_bytes(),
                    "application/gzip",
                )
            },
        )
        if resp.status_code >= 400:
            raise WebSessionError(
                f"App install failed: HTTP {resp.status_code}", kind="web"
            )


def _expect_ok(resp: requests.Response, what: str) -> None:
    """Raise unless the form handler answered with JSON status OK."""
    try:
        result: dict[str, Any] = resp.json()
    except ValueError:
        raise WebSessionError(
            f"{what} failed: HTTP {resp.status_code}: "
            f"unexpected response: {resp.text[:200]!r}",
            kind="web",
        ) from None
    if result.get("status") != "OK":
        raise WebSessionError(
            f"{what} failed: {result.get('msg', 'unknown error')}", kind="web"
        )
