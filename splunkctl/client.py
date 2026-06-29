"""SDK wrapper — lazy connection and auth resolution.

Includes Web UI upload support for operations the REST API cannot
handle remotely (e.g. lookup file upload requires server-side staging).
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import click
import splunklib.client as splunk_client

from splunkctl import config as cfg_mod


class SplunkClient:
    """Lazy-initializing Splunk SDK client.

    Connection is established on first access to ``.service``.
    Help, config, and offline commands never trigger auth.
    """

    def __init__(  # noqa: D107
        self,
        *,
        config_path: Path | None = None,
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

            cfg = cfg_mod.load(self._config_path)
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

            if self._timeout:
                connect_args["timeout"] = self._timeout

            self._service = splunk_client.connect(**connect_args)

        return self._service

    def _ensure_web_session(self) -> _WebSession:
        if self._web_session is None:
            cfg = cfg_mod.load(self._config_path)
            cfg.update(self._overrides)
            self._web_session = _WebSession(
                self.service, verify=bool(cfg.get("verify", False))
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


class _WebSession:
    """Manages authentication and uploads via Splunk Web UI."""

    def __init__(self, service: Any, *, verify: bool = True) -> None:
        self._host: str = service.host
        self._username: str = service.username
        self._password: str = service.password
        if not self._username or not self._password:
            raise RuntimeError(
                "Lookup upload requires username/password authentication. "
                "Token-only auth cannot authenticate to Splunk Web UI."
            )

        web_conf = service.confs["web"]["settings"]
        self._web_port = int(web_conf["httpport"])
        self._web_ssl = str(web_conf.content.get("enableSplunkWebSSL", "0")) == "1"

        self._cookies = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        if not verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # noqa: S501
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookies),
            urllib.request.HTTPSHandler(context=ctx),
        )
        self._csrf_token: str | None = None
        self._logged_in = False

    @property
    def _base_url(self) -> str:
        scheme = "https" if self._web_ssl else "http"
        return f"{scheme}://{self._host}:{self._web_port}"

    def _login(self) -> None:
        """Authenticate to Splunk Web and obtain session cookies."""
        login_url = f"{self._base_url}/en-US/account/login"
        resp = self._opener.open(login_url)  # noqa: S310
        page = resp.read().decode("utf-8")

        m = re.search(r'"cval"\s*:\s*(\d+)', page)
        cval = m.group(1) if m else "0"

        data = urllib.parse.urlencode(
            {
                "username": self._username,
                "password": self._password,
                "cval": cval,
            }
        ).encode()
        resp = self._opener.open(login_url, data)  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
        if body.get("status") == "fail":
            msg = body.get("msg", "unknown error")
            raise RuntimeError(f"Splunk Web login failed: {msg}")

        for cookie in self._cookies:
            if cookie.name.startswith("splunkweb_csrf_token"):
                self._csrf_token = cookie.value
                break
        if not self._csrf_token:
            raise RuntimeError("Could not obtain CSRF token from Splunk Web")
        self._logged_in = True

    def _multipart_post(
        self,
        url: str,
        fields: list[tuple[str, str]],
        file_field: str,
        file_name: str,
        file_data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bytes:
        """Build and send a multipart/form-data POST."""
        if not self._logged_in:
            self._login()

        boundary = uuid.uuid4().hex
        body = b""
        for field_name, value in fields:
            body += f"--{boundary}\r\n".encode()
            body += (
                f'Content-Disposition: form-data; name="{field_name}"\r\n'
                f"\r\n"
                f"{value}\r\n"
            ).encode()

        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{file_field}";'
            f' filename="{file_name}"\r\n'
            f"Content-Type: {content_type}\r\n"
            f"\r\n"
        ).encode()
        body += file_data
        body += f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(  # noqa: S310
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        resp = self._opener.open(req)  # noqa: S310
        return bytes(resp.read())

    def upload_lookup(
        self,
        name: str,
        file_path: Path,
        *,
        app: str = "search",
        update: bool = False,
    ) -> None:
        """Upload a lookup file via multipart form POST."""
        if update:
            url = (
                f"{self._base_url}/en-US/manager/{app}"
                f"/data/lookup-table-files/{urllib.parse.quote(name)}"
            )
            action = "edit"
        else:
            url = f"{self._base_url}/en-US/manager/{app}/data/lookup-table-files/_new"
            action = "new"

        fields: list[tuple[str, str]] = [
            ("__action", action),
            ("__redirect", ""),
            ("__ns", app),
            ("splunk_form_key", self._csrf_token or ""),
        ]
        if not update:
            fields.append(("name", name))

        resp_body = self._multipart_post(
            url,
            fields,
            file_field="spl-ctrl_lookupfile",
            file_name=name,
            file_data=file_path.read_bytes(),
            content_type="text/csv",
        )
        result = json.loads(resp_body.decode("utf-8"))
        if result.get("status") != "OK":
            msg = result.get("msg", "unknown error")
            raise RuntimeError(f"Lookup upload failed: {msg}")

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
        resp = self._opener.open(upload_url)  # noqa: S310
        page = resp.read().decode("utf-8")

        m = re.search(
            r'name="state"\s+[^>]*value="([^"]*)"',
            page,
        )
        state = m.group(1) if m else ""

        fields: list[tuple[str, str]] = [
            ("state", state),
            ("splunk_form_key", self._csrf_token or ""),
        ]
        if force:
            fields.append(("force", "1"))

        self._multipart_post(
            upload_url,
            fields,
            file_field="appfile",
            file_name=file_path.name,
            file_data=file_path.read_bytes(),
            content_type="application/gzip",
        )


def get_client(ctx: click.Context) -> SplunkClient:
    """Build a SplunkClient from Click context. Does not connect."""
    obj: dict[str, Any] = ctx.ensure_object(dict)
    return SplunkClient(
        config_path=Path(obj["config"]) if obj.get("config") else None,
        timeout=obj.get("timeout", 30),
        debug=obj.get("debug", False),
    )
