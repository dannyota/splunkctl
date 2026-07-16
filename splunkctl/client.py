"""SDK wrapper — lazy connection and auth resolution.

Includes Web UI upload support for operations the REST API cannot
handle remotely (e.g. lookup file upload requires server-side staging).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

import click
import requests
import splunklib.client as splunk_client
import urllib3

from splunkctl import config as cfg_mod
from splunkctl.errors import WebSessionError

_tls_warned: bool = False


def _warn_tls_off() -> None:
    """Print one warning per process when TLS verification is disabled."""
    global _tls_warned  # noqa: PLW0603
    if not _tls_warned:
        _tls_warned = True
        click.echo(
            "Warning: TLS certificate verification is disabled for this connection.",
            err=True,
        )


class SplunkClient:
    """Lazy-initializing Splunk SDK client.

    Connection is established on first access to ``.service``.
    Help, config, and offline commands never trigger auth.
    """

    def __init__(  # noqa: D107
        self,
        *,
        config_path: Path | None = None,
        profile: str | None = None,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        scheme: str | None = None,
        app: str | None = None,
        owner: str | None = None,
        verify: bool | None = None,
        timeout: int = 30,
        debug: bool = False,
    ) -> None:
        self._config_path = config_path
        self._profile = profile
        self._overrides: dict[str, Any] = {
            k: v
            for k, v in {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "token": token,
                "scheme": scheme,
                "app": app,
                "owner": owner,
                "verify": verify,
            }.items()
            if v is not None
        }
        self._timeout = timeout
        self._debug = debug
        self._service: Any = None
        self._web_session: _WebSession | None = None

    @property
    def service(self) -> Any:
        """Connect on first access."""
        if self._service is None:
            if self._debug:
                import logging

                logging.basicConfig(level=logging.DEBUG)
                logging.getLogger("splunklib").setLevel(logging.DEBUG)

            cfg = cfg_mod.load(self._config_path, profile=self._profile)
            cfg.update(self._overrides)

            connect_args: dict[str, Any] = {
                "host": cfg.get("host", "localhost"),
                "port": int(cfg.get("port", 8089)),
                "scheme": cfg.get("scheme", "https"),
            }

            if cfg.get("token"):
                connect_args["splunkToken"] = cfg["token"]
            else:
                connect_args["username"] = cfg.get("username", "")
                connect_args["password"] = cfg.get("password", "")

            if cfg.get("app"):
                connect_args["app"] = cfg["app"]
            if cfg.get("owner"):
                connect_args["owner"] = cfg["owner"]

            if not cfg.get("verify", False):
                connect_args["verify"] = False
                _warn_tls_off()

            if self._timeout:
                connect_args["timeout"] = self._timeout

            self._service = splunk_client.connect(**connect_args)

        return self._service

    def _ensure_web_session(self) -> _WebSession:
        if self._web_session is None:
            cfg = cfg_mod.load(self._config_path, profile=self._profile)
            cfg.update(self._overrides)
            self._web_session = _WebSession(
                self.service,
                verify=bool(cfg.get("verify", False)),
                debug=self._debug,
                timeout=self._timeout or 30,
            )
        return self._web_session

    def upload_lookup(
        self,
        name: str,
        file_path: Path,
        *,
        app: str = "search",
        update: bool = False,
    ) -> None:
        """Upload a lookup CSV via the Splunk Web UI form handler."""
        self._ensure_web_session().upload_lookup(
            name, file_path, app=app, update=update
        )

    def install_app(
        self,
        file_path: Path,
        *,
        force: bool = False,
    ) -> None:
        """Install a .spl/.tar.gz app package via the Splunk Web UI."""
        self._ensure_web_session().install_app(file_path, force=force)

    def set_acl(self, entity: Any, *, sharing: str, owner: str | None = None) -> None:
        """Change an entity's sharing level via its ACL endpoint.

        Args:
            entity: Any SDK entity (saved search, dashboard, conf stanza...).
            sharing: One of user, app, global.
            owner: Defaults to the entity's current owner, else "nobody".
        """
        acl: dict[str, Any] = dict(entity.access)
        entity.acl_update(sharing=sharing, owner=owner or acl.get("owner", "nobody"))


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
        verify: bool = True,
        debug: bool = False,
        timeout: int = 30,
    ) -> None:
        self._host: str = service.host
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
        self._session = requests.Session()
        self._session.verify = verify
        if not verify:
            # verify=false is an explicit config choice (lab/self-signed);
            # without this every request spams InsecureRequestWarning.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._csrf_token: str | None = None
        self._logged_in = False

    @property
    def _base_url(self) -> str:
        scheme = "https" if self._web_ssl else "http"
        return f"{scheme}://{self._host}:{self._web_port}"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        if self._debug:
            click.echo(f"web {method} {url} -> {resp.status_code}", err=True)
        return resp

    def _login(self) -> None:
        """Authenticate to Splunk Web and obtain session cookies."""
        login_url = f"{self._base_url}/en-US/account/login"
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
        if body.get("status") == "fail":
            msg = body.get("msg", "unknown error")
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
            f"{what} failed: HTTP {resp.status_code} — "
            f"unexpected response: {resp.text[:200]!r}",
            kind="web",
        ) from None
    if result.get("status") != "OK":
        raise WebSessionError(
            f"{what} failed: {result.get('msg', 'unknown error')}", kind="web"
        )


def rest_get_json(
    svc: Any,
    path: str,
    *,
    owner: str | None = None,
    app: str | None = None,
    **query: Any,
) -> Any:
    """GET a REST path via the SDK's authenticated session and parse JSON.

    Always passes ``output_mode=json`` so endpoints that default to Atom
    XML (e.g. ``storage/collections/config``) come back as JSON just like
    the KV store data endpoints already do. Any raised ``HTTPError`` (or
    connection failure) is left to propagate — callers rely on
    ``splunkctl.errors.classify`` at the top level to turn it into a
    clean error envelope.
    """
    resp = svc.get(path, owner=owner, app=app, output_mode="json", **query)
    return json.loads(resp.body.read())


def rest_post_json(
    svc: Any,
    path: str,
    body: Any,
    *,
    owner: str | None = None,
    app: str | None = None,
) -> Any:
    """POST a JSON-encoded body to a REST path and parse the JSON response.

    The KV store data API (``storage/collections/data/...``) requires
    ``Content-Type: application/json`` on the request body and always
    responds with JSON — unlike most Splunk config endpoints, which use
    ``x-www-form-urlencoded`` params via plain keyword arguments. Returns
    ``None`` for an empty response body (e.g. some KV store writes).
    """
    resp = svc.post(
        path,
        owner=owner,
        app=app,
        headers=[("Content-Type", "application/json")],
        body=json.dumps(body),
    )
    raw = resp.body.read()
    return json.loads(raw) if raw else None


def get_client(ctx: click.Context) -> SplunkClient:
    """Build a SplunkClient from Click context. Does not connect."""
    obj: dict[str, Any] = ctx.ensure_object(dict)
    return SplunkClient(
        config_path=Path(obj["config"]) if obj.get("config") else None,
        profile=obj.get("profile"),
        timeout=obj.get("timeout", 30),
        debug=obj.get("debug", False),
    )
