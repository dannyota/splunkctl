"""SDK wrapper — lazy connection and auth resolution."""

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


def get_client(ctx: click.Context) -> SplunkClient:
    """Build a SplunkClient from Click context. Does not connect."""
    obj: dict[str, Any] = ctx.ensure_object(dict)
    return SplunkClient(
        config_path=Path(obj["config"]) if obj.get("config") else None,
        timeout=obj.get("timeout", 30),
        debug=obj.get("debug", False),
    )
