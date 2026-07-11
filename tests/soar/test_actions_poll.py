"""Tests for soar actions — polling, cancelled status, error propagation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
_SLEEP = "splunkctl.commands.soar.actions.time.sleep"
_MONO = "splunkctl.commands.soar.actions.time.monotonic"

_ASSET: dict[str, Any] = {"id": 10, "name": "google_dns", "app_id": 55}
_RUN_RESP: dict[str, Any] = {"success": True, "id": 999}
_S_PEND: dict[str, Any] = {"id": 999, "status": "pending", "action": "lookup domain"}
_S_RUN: dict[str, Any] = {"id": 999, "status": "running", "action": "lookup domain"}
_S_OK: dict[str, Any] = {"id": 999, "status": "success", "action": "lookup domain"}
_S_FAIL: dict[str, Any] = {"id": 999, "status": "failed", "action": "lookup domain"}
_APP_RUNS: dict[str, Any] = {
    "count": 1,
    "data": [
        {
            "id": 1001,
            "action": "lookup domain",
            "app_name": "DNS",
            "asset": "google_dns",
            "status": "success",
            "result_data": [
                {"parameter": {"domain": "example.com"}, "data": {"A": "93.184.215.14"}}
            ],
        }
    ],
}


def _guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


def _run_args(
    *extra: str,
    yes: bool = True,
    action: str = "lookup domain",
    asset: str = "google_dns",
    container: str = "42",
) -> list[str]:
    """Build a common ``soar actions run`` argument list."""
    args: list[str] = []
    if yes:
        args.append("--yes")
    args += [
        "soar",
        "actions",
        "run",
        "--action",
        action,
        "--asset",
        asset,
        "--container",
        container,
    ]
    args.extend(extra)
    return args


class TestActionRunWait:
    @patch(_SLEEP)
    @patch(_MONO)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_polls_until_success(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        mono: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.side_effect = [
            {"count": 1, "data": [_ASSET]},
            _S_PEND,
            _S_RUN,
            _S_OK,
            _APP_RUNS,
        ]
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        mono.side_effect = [0, 1, 2, 3, 4]
        r = CliRunner().invoke(
            cli,
            _run_args("--param", "domain=example.com", "--wait"),
        )
        assert r.exit_code == 0
        assert c.get.call_count == 5
        _s.assert_called()

    @patch(_SLEEP)
    @patch(_MONO)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_timeout(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        mono: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.side_effect = [
            {"count": 1, "data": [_ASSET]},
            _S_PEND,
        ]
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        mono.side_effect = [0, 100]
        r = CliRunner().invoke(
            cli,
            _run_args("--wait", "--timeout", "60"),
        )
        assert r.exit_code == 1

    @patch(_SLEEP)
    @patch(_MONO)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_failed_status(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        mono: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.side_effect = [
            {"count": 1, "data": [_ASSET]},
            _S_FAIL,
            _APP_RUNS,
        ]
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        mono.side_effect = [0, 1, 2]
        r = CliRunner().invoke(
            cli,
            _run_args("--wait"),
        )
        assert r.exit_code == 1

    @patch(_SLEEP)
    @patch(_MONO)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cancelled_terminates_poll(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        mono: MagicMock,
        _s: MagicMock,
    ) -> None:
        """Poll recognises 'cancelled' as a terminal status."""
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        _s_cancelled = {"id": 999, "status": "cancelled", "action": "lookup domain"}
        c.get.side_effect = [
            {"count": 1, "data": [_ASSET]},
            _S_PEND,
            _s_cancelled,
        ]
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        mono.side_effect = [0, 1, 2, 3]
        r = CliRunner().invoke(
            cli,
            _run_args("--wait"),
        )
        # cancelled is terminal — no timeout message
        out = r.output + (r.stderr or "")
        assert "did not complete" not in out
        assert "cancelled" in out

    @patch(_SLEEP)
    @patch(_MONO)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_mid_poll_soar_error_surfaces(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        mono: MagicMock,
        _s: MagicMock,
    ) -> None:
        """A SOARError mid-poll shows the real error, not a timeout."""
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.side_effect = [
            {"count": 1, "data": [_ASSET]},
            _S_PEND,
            SOARError("Unauthorized", kind="auth", http_status=401),
        ]
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        mono.side_effect = [0, 1, 2, 3]
        r = CliRunner().invoke(
            cli,
            _run_args("--wait"),
        )
        assert r.exit_code == 1
        out = r.output + (r.stderr or "")
        assert "Unauthorized" in out
        assert "did not complete" not in out


class TestResolveAppIdErrorHandling:
    """_resolve_app_id re-raises SOARError; returns None for empty data."""

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_server_error_propagates(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        """A 500 during asset lookup shows the server error."""
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.side_effect = SOARError(
            "Internal Server Error", kind="server", http_status=500
        )
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            _run_args(asset="myasset"),
        )
        assert r.exit_code == 1
        out = r.output + (r.stderr or "")
        assert "Internal Server Error" in out

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_empty_data_returns_not_found(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        """Empty data from asset lookup gives 'not found' message."""
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.return_value = {"count": 0, "data": []}
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            _run_args(asset="nonexistent"),
        )
        assert r.exit_code == 1
        out = r.output + (r.stderr or "")
        assert "not found" in out
