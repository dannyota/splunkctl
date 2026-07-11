"""Tests for soar platform commands — test, info, health, license."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH_RESOLVE = "splunkctl.commands.soar._client.cfg_mod.resolve_soar"
_PATCH_CLIENT = "splunkctl.commands.soar._client.SOARClient"


def _soar_cfg(
    *,
    host: str = "soar.test",
    port: int = 8443,
    token: str = "tok123",  # noqa: S107
    verify: bool = False,
) -> dict[str, Any]:
    return {"host": host, "port": port, "token": token, "verify": verify}


def _mock_client(responses: dict[str, Any] | None = None) -> MagicMock:
    """Return a mock SOARClient whose .get() returns from *responses*."""
    client = MagicMock()
    if responses:
        client.get.side_effect = lambda path, **kw: responses.get(path, {})
    return client


# -------------------------------------------------------------------
# soar test
# -------------------------------------------------------------------


class TestSoarTest:
    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_success(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = _soar_cfg()
        client = _mock_client({"version": {"version": "8.5.0.248", "build": "abcdef"}})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "test"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["version"] == "8.5.0.248"
        assert data[0]["status"] == "ok"

    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_connection_error(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = _soar_cfg()
        client = _mock_client()
        client.get.side_effect = requests.exceptions.ConnectionError("refused")
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "test"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "connection"

    @patch(_PATCH_RESOLVE)
    def test_no_host_configured(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = {"port": 8443, "verify": False}

        result = CliRunner().invoke(cli, ["--json", "soar", "test"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"


# -------------------------------------------------------------------
# soar info
# -------------------------------------------------------------------


class TestSoarInfo:
    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_success(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = _soar_cfg()
        client = _mock_client(
            {
                "version": {"version": "8.5.0.248", "build": "abcdef"},
                "system_info": {
                    "fqdn": "soar.lab.local",
                    "ssh_port": 22,
                    "rsa_key_size": 2048,
                },
            }
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "info"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["version"] == "8.5.0.248"
        assert data[0]["fqdn"] == "soar.lab.local"


# -------------------------------------------------------------------
# soar health
# -------------------------------------------------------------------


class TestSoarHealth:
    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_healthy_daemons(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = _soar_cfg()
        health_data: dict[str, Any] = {
            "status": {
                "decided": "running",
                "nginx": "running",
                "postgres": "running",
            },
            "services": {
                "decided": [{"time": "2026-07-01", "pid": 123}],
                "nginx": [{"time": "2026-07-01", "pid": 456}],
                "postgres": [{"time": "2026-07-01", "pid": 789}],
            },
        }
        responses: dict[str, Any] = {
            "health": health_data,
            "warm_standby": {"status": "off"},
            "cluster_node": {"count": 0, "data": []},
        }
        client = _mock_client(responses)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "health"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Should have daemon rows
        daemons = [r for r in data if r.get("type") == "daemon"]
        assert len(daemons) >= 3

    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_warm_standby_off(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = _soar_cfg()
        from splunkctl.soar.client import SOARError

        def side_effect(path: str, **kw: Any) -> Any:
            if path == "health":
                return {}
            if path == "warm_standby":
                return {"status": "off"}
            if path == "cluster_node":
                raise SOARError("not found", kind="not_found", http_status=404)
            return {}

        client = MagicMock()
        client.get.side_effect = side_effect
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "health"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        standby_rows = [r for r in data if r.get("type") == "warm_standby"]
        assert len(standby_rows) == 1
        assert standby_rows[0]["status"] == "off"

    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_cluster_graceful_empty(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """cluster_node errors are swallowed (lab is unclustered)."""
        mock_resolve.return_value = _soar_cfg()
        from splunkctl.soar.client import SOARError

        def side_effect(path: str, **kw: Any) -> Any:
            if path == "health":
                return {}
            if path == "warm_standby":
                raise SOARError("not found", kind="not_found", http_status=404)
            if path == "cluster_node":
                raise SOARError("not found", kind="not_found", http_status=404)
            return {}

        client = MagicMock()
        client.get.side_effect = side_effect
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "health"])
        assert result.exit_code == 0


# -------------------------------------------------------------------
# soar license
# -------------------------------------------------------------------


class TestSoarLicense:
    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_license_data(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = _soar_cfg()
        license_data: dict[str, Any] = {
            "license_type": "community",
            "max_allowed_actions_per_day": 100,
            "valid_until": "2027-01-01T00:00:00Z",
            "actions_used_today": 5,
        }
        client = _mock_client({"license": license_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "license"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["license_type"] == "community"
        assert data[0]["max_allowed_actions_per_day"] == 100


# -------------------------------------------------------------------
# soar group appears in commands --json
# -------------------------------------------------------------------


class TestCommandsJson:
    def test_soar_in_commands(self) -> None:
        result = CliRunner().invoke(cli, ["commands", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["name"] for c in data["commands"]]
        assert "soar" in names


# -------------------------------------------------------------------
# SOARError flows through _CLI.invoke error handler
# -------------------------------------------------------------------


class TestSOARErrorHandler:
    @patch(_PATCH_CLIENT)
    @patch(_PATCH_RESOLVE)
    def test_soar_error_classified(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """SOARError with kind=auth produces an auth error envelope."""
        mock_resolve.return_value = _soar_cfg()
        from splunkctl.soar.client import SOARError

        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not authenticated", kind="auth", http_status=401
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "info"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "auth"
        assert payload["error"]["http_status"] == 401
