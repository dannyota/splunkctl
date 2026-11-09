"""SDK wrapper — lazy connection and auth resolution.

Includes Web UI upload support for operations the REST API cannot
handle remotely (e.g. lookup file upload requires server-side staging).
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Any

import click
import splunklib.client as splunk_client
from splunklib.binding import handler

from splunkctl import config as cfg_mod
from splunkctl.errors import WebSessionError
from splunkctl.request_context import Invocation, readonly
from splunkctl.rest_adapters import Dashboards, HECTokens, LookupTableFiles
from splunkctl.transport import sdk_handler
from splunkctl.web_session import _WebSession

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
        self._identity = Invocation("library", False)
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

            self._siem_auth(cfg, connect_args)

            if cfg.get("app"):
                connect_args["app"] = cfg["app"]
            if cfg.get("owner"):
                connect_args["owner"] = cfg["owner"]

            connect_args["verify"] = bool(cfg.get("verify", True))
            if not connect_args["verify"]:
                _warn_tls_off()

            if self._timeout:
                connect_args["timeout"] = self._timeout

            host = str(connect_args["host"])
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            origin = f"{connect_args['scheme']}://{host}:{connect_args['port']}"
            connect_args["handler"] = sdk_handler(
                handler(timeout=self._timeout or None, verify=connect_args["verify"]),
                origin,
                self._identity,
            )
            connect_args["autologin"] = False
            self._service = splunk_client.connect(**connect_args)

        return self._service

    @cached_property
    def dashboards(self) -> Dashboards:
        """Return local dashboard REST adapters."""
        return Dashboards(self.service)

    @cached_property
    def lookup_table_files(self) -> LookupTableFiles:
        """Return local lookup metadata REST adapters."""
        return LookupTableFiles(self.service)

    @cached_property
    def hec_tokens(self) -> HECTokens:
        """Return local HEC REST adapters."""
        return HECTokens(self.service)

    def _siem_auth(self, cfg: dict[str, Any], connect_args: dict[str, Any]) -> None:
        """Populate SIEM auth into ``connect_args``.

        Preference order: browser session, then token, then username/password.
        When browser mode is configured but the session is missing or expired,
        re-probe the login route and fall back to token/password when SAML has
        since been removed, instead of telling the user to run a doomed login.
        """
        if cfg.get("auth_mode") != "browser":
            if cfg.get("token"):
                connect_args["splunkToken"] = cfg["token"]
            else:
                connect_args["username"] = cfg.get("username", "")
                connect_args["password"] = cfg.get("password", "")
            return

        from splunkctl.auth import adapters, detector
        from splunkctl.auth import session as sess_mod

        ta = sess_mod.resolve_target(
            self._config_path, self._profile, "siem", timeout=self._timeout
        )
        rec = sess_mod.load(ta.profile, "siem", expected_origin=ta.web_url)
        if rec is not None:
            status = adapters.get_adapter("siem").validate(
                rec.values,
                api_base=ta.api_base,
                verify=ta.verify,
                timeout=ta.timeout,
            )
            if status == "valid":
                connect_args["splunkToken"] = rec.values["session_key"]
                return
            if status == "unreachable":
                raise WebSessionError(
                    "SIEM is unreachable while checking the browser session.",
                    kind="connection",
                )
            sess_mod.delete(ta.profile, "siem")

        if readonly():
            raise WebSessionError(
                "SIEM browser session is missing or expired; read-only requires "
                "an existing session. Run `splunkctl auth login --target siem` first.",
                kind="auth",
            )

        # Session is missing or expired. Only direct the user to log in when
        # the SIEM is still SAML-configured; otherwise fall back to creds.
        if detector.probe(ta.login_url, verify=ta.verify, timeout=ta.timeout) == (
            "browser"
        ):
            raise WebSessionError(
                "SIEM browser session is missing. Run "
                "`splunkctl auth login --target siem`.",
                kind="auth",
            )
        click.echo(
            "Warning: SIEM is no longer SAML-authenticated; using "
            "token/password auth. Run `splunkctl config init` to record it.",
            err=True,
        )
        if cfg.get("token"):
            connect_args["splunkToken"] = cfg["token"]
        else:
            connect_args["username"] = cfg.get("username", "")
            connect_args["password"] = cfg.get("password", "")

    def _ensure_web_session(self) -> _WebSession:
        if self._web_session is None:
            cfg = cfg_mod.load(self._config_path, profile=self._profile)
            cfg.update(self._overrides)
            self._web_session = _WebSession(
                self.service,
                identity=self._identity,
                verify=bool(cfg.get("verify", True)),
                debug=self._debug,
                timeout=self._timeout or 30,
                web_url=cfg.get("web_url"),
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
        config_path=Path(obj.get("config") or cfg_mod.DEFAULT_PATH),
        profile=obj.get("profile"),
        timeout=obj.get("timeout", 30),
        debug=obj.get("debug", False),
    )
