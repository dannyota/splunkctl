"""Tests for soar actions — list, status, results, cancel."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


_STATUS_SUCCESS: dict[str, Any] = {
    "id": 999,
    "status": "success",
    "action": "lookup domain",
    "container": 42,
}

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
                {
                    "parameter": {"domain": "example.com"},
                    "data": {"A": "93.184.215.14"},
                }
            ],
        }
    ],
}


class TestActionList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_actions(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "data": [
                {"id": 100, "status": "success", "action": "lookup domain"},
                {"id": 101, "status": "failed", "action": "run query"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "actions", "list", "--container", "42"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once()
        args, kwargs = client.get.call_args
        assert args[0] == "container/42/actions"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_all(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "data": [{"id": 100, "status": "success"}],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "actions", "list"])
        assert result.exit_code == 0
        args, _ = client.get.call_args
        assert args[0] == "action_run"


class TestActionListPagination:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_limit_offset(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        """--offset with --limit computes page = offset // limit."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            ["--json", "soar", "actions", "list", "--limit", "5", "--offset", "10"],
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params["page_size"] == 5
        assert params["page"] == 2  # 10 // 5

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_offset_without_limit_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        """--offset without --limit exits 1 with a usage error."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "actions", "list", "--offset", "20"]
        )
        assert result.exit_code == 1
        assert "--offset requires --limit" in (result.output + (result.stderr or ""))
        client.get.assert_not_called()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_offset_not_multiple_of_limit_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        """--offset must be a multiple of --limit."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "actions", "list", "--limit", "5", "--offset", "7"],
        )
        assert result.exit_code == 1
        assert "multiple" in (result.output + (result.stderr or ""))
        client.get.assert_not_called()


class TestActionStatus:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_status(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _STATUS_SUCCESS
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "actions", "status", "999"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once_with(
            "action_run/999",
            params={},
        )

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_status_not_found(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found",
            kind="not_found",
            http_status=404,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "actions", "status", "9999"],
        )
        assert result.exit_code == 1


class TestActionResults:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_results(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _APP_RUNS
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "actions", "results", "999"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once_with(
            "action_run/999/app_runs",
            params={},
        )


class TestActionCancel:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cancel_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()

        result = CliRunner().invoke(
            cli,
            ["soar", "actions", "cancel", "999"],
        )
        assert result.exit_code == 0
        out = result.output + (result.stderr or "")
        assert "DRY RUN" in out

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cancel_applies(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "actions", "cancel", "999"],
        )
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "action_run/999",
            body={"cancel": True},
        )

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cancel_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "Not found",
            kind="not_found",
            http_status=404,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "actions", "cancel", "9999"],
        )
        assert result.exit_code == 1
