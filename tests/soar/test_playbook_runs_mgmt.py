"""Tests for soar playbooks runs — list, get, cancel."""

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


class TestRunsList:
    """GET /rest/playbook_run — read-only."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_runs_list(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 1, "status": "success", "playbook": 5}],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "playbooks", "runs", "list"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once()
        assert client.get.call_args[0][0] == "playbook_run"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_runs_list_with_filters(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "playbooks",
                "runs",
                "list",
                "--container",
                "42",
                "--status",
                "failed",
            ],
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["_filter_container"] == 42
        assert params["_filter_status"] == '"failed"'


class TestRunsGet:
    """GET /rest/playbook_run/<id> — read-only."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_runs_get(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 10,
            "status": "success",
            "playbook": 5,
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "playbooks", "runs", "get", "10"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once_with(
            "playbook_run/10",
            params={},
        )

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_runs_get_blocks(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        """--blocks fetches block_results sub-endpoint."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"block": "block_1", "status": "success"},
                {"block": "block_2", "status": "success"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "playbooks",
                "runs",
                "get",
                "10",
                "--blocks",
            ],
        )
        assert result.exit_code == 0
        client.get.assert_called_once_with(
            "playbook_run/10/block_results",
            params={},
        )

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_runs_get_not_found(
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
            ["--json", "soar", "playbooks", "runs", "get", "999"],
        )
        assert result.exit_code == 1
        assert "not_found" in result.stderr


class TestRunsCancel:
    """POST /rest/playbook_run/<id> {cancel: true} — guarded."""

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
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "playbooks", "runs", "cancel", "10"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cancel_with_yes(
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
            ["--yes", "soar", "playbooks", "runs", "cancel", "10"],
        )
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "playbook_run/10",
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
            "Run already completed",
            kind="error",
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "runs",
                "cancel",
                "10",
            ],
        )
        assert result.exit_code == 1
        assert "already completed" in result.stderr
