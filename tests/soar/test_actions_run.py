"""Tests for soar actions run — payload, polling, wait, timeout."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
_SLEEP = "splunkctl.commands.soar.actions.time.sleep"
_MONO = "splunkctl.commands.soar.actions.time.monotonic"

_ASSET = {"id": 10, "name": "google_dns", "app_id": 55}
_RUN_RESP: dict[str, Any] = {"success": True, "id": 999}
_S_PEND = {"id": 999, "status": "pending", "action": "lookup domain"}
_S_RUN = {"id": 999, "status": "running", "action": "lookup domain"}
_S_OK = {"id": 999, "status": "success", "action": "lookup domain"}
_S_FAIL = {"id": 999, "status": "failed", "action": "lookup domain"}
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


class TestActionRun:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        r = CliRunner().invoke(
            cli,
            _run_args("--param", "domain=example.com", yes=False),
        )
        assert r.exit_code == 0
        assert "DRY RUN" in r.output + (r.stderr or "")

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_applies(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.return_value = {"count": 1, "data": [_ASSET]}
        c.post.return_value = _RUN_RESP
        cls.return_value = c

        r = CliRunner().invoke(
            cli,
            _run_args("--param", "domain=example.com"),
        )
        assert r.exit_code == 0
        c.post.assert_called_once()
        body = c.post.call_args[1]["body"]
        assert body["action"] == "lookup domain"
        assert body["container_id"] == 42
        assert body["targets"][0]["assets"] == ["google_dns"]
        assert body["targets"][0]["app_id"] == 55
        assert body["targets"][0]["parameters"] == [
            {"domain": "example.com"},
        ]

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_explicit_app_id(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            _run_args("--app", "55", "--param", "domain=example.com"),
        )
        assert r.exit_code == 0
        assert c.post.call_args[1]["body"]["targets"][0]["app_id"] == 55
        c.get.assert_not_called()

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_asset_not_found(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
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

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_multiple_assets(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        a2 = {"id": 11, "name": "custom_dns", "app_id": 55}

        def side(path: str, **kw: Any) -> dict[str, Any]:
            f = kw.get("params", {}).get("_filter_name", "")
            if "google_dns" in f:
                return {"count": 1, "data": [_ASSET]}
            if "custom_dns" in f:
                return {"count": 1, "data": [a2]}
            return {"count": 0, "data": []}

        c.get.side_effect = side
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "actions",
                "run",
                "--action",
                "lookup domain",
                "--asset",
                "google_dns",
                "--asset",
                "custom_dns",
                "--container",
                "42",
                "--param",
                "domain=example.com",
            ],
        )
        assert r.exit_code == 0
        tgts = c.post.call_args[1]["body"]["targets"]
        assert tgts[0]["assets"] == ["google_dns", "custom_dns"]

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_type_flag(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.return_value = {"count": 1, "data": [_ASSET]}
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            _run_args("--type", "investigate"),
        )
        assert r.exit_code == 0
        assert c.post.call_args[1]["body"]["type"] == "investigate"

    @patch(_SLEEP)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_multiple_params(
        self,
        res: MagicMock,
        cls: MagicMock,
        g: MagicMock,
        _s: MagicMock,
    ) -> None:
        res.return_value = _WRITE_CFG
        g.return_value = _guard_cfg()
        c = MagicMock()
        c.get.return_value = {"count": 1, "data": [_ASSET]}
        c.post.return_value = _RUN_RESP
        cls.return_value = c
        r = CliRunner().invoke(
            cli,
            _run_args("--param", "domain=example.com", "--param", "type=A"),
        )
        assert r.exit_code == 0
        p = c.post.call_args[1]["body"]["targets"][0]["parameters"]
        assert p == [{"domain": "example.com", "type": "A"}]


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
