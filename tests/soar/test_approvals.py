"""Tests for soar approvals — list, get, respond."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_BANNER = "splunkctl.guard.soar_banner"


# ---------------------------------------------------------------------------
# approvals list
# ---------------------------------------------------------------------------


class TestApprovalsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_all(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """List all approvals via GET /rest/approval."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "message": "Approve block?", "status": "pending"},
                {"id": 2, "message": "Escalate?", "status": "approved"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "approvals", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["status"] == "pending"
        client.get.assert_called_once()
        path_arg = client.get.call_args[0][0]
        assert path_arg == "approval"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_by_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--container queries the per-container approvals endpoint."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {"id": 3, "message": "Allow?", "status": "pending"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "approvals", "list", "--container", "42"]
        )
        assert result.exit_code == 0
        path_arg = client.get.call_args[0][0]
        assert path_arg == "container/42/approvals"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_pending_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--pending adds a status filter for pending approvals."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "approvals", "list", "--pending"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1].get("params", {})
        assert params.get("_filter_status") == '"pending"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_container_and_pending(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--container and --pending combine."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "approvals",
                "list",
                "--container",
                "10",
                "--pending",
            ],
        )
        assert result.exit_code == 0
        path_arg = client.get.call_args[0][0]
        assert path_arg == "container/10/approvals"
        params = client.get.call_args[1].get("params", {})
        assert params.get("_filter_status") == '"pending"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Empty list returns exit 0 with empty JSON array."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "approvals", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """API error exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("server error", kind="http", http_status=500)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "approvals", "list"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# approvals get
# ---------------------------------------------------------------------------


class TestApprovalsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_detail(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Get fetches detail_summary_view for an approval."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 5,
            "message": "Block IP?",
            "status": "pending",
            "responses": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "approvals", "get", "5"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == 5
        path_arg = client.get.call_args[0][0]
        assert path_arg == "approval/5"
        params = client.get.call_args[1].get("params", {})
        assert params.get("_detail") == "detail_summary_view"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Missing approval exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "approvals", "get", "999"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# approvals respond
# ---------------------------------------------------------------------------


class TestApprovalsRespond:
    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """Default (no --yes) prints dry-run, does NOT post."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "approvals", "respond", "5", "approve"]
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_approve_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """--yes posts approve to external_prompt endpoint."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "approvals",
                "respond",
                "5",
                "approve",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "external_prompt/5"
        body = call_args[1]["body"]
        assert body["status"] == "approve"

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_deny_with_message(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """--message includes a response message in the POST body."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "approvals",
                "respond",
                "5",
                "deny",
                "--message",
                "Insufficient evidence",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["status"] == "deny"
        assert body["message"] == "Insufficient evidence"

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_invalid_action(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """Invalid action (not approve/deny) is a Click usage error."""
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "approvals",
                "respond",
                "5",
                "maybe",
            ],
        )
        assert result.exit_code != 0

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """API error on respond exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "already responded", kind="conflict", http_status=409
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "approvals",
                "respond",
                "5",
                "approve",
            ],
        )
        assert result.exit_code == 1

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_respond_approve_with_message(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """Approve with --message includes the message."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "approvals",
                "respond",
                "5",
                "approve",
                "--message",
                "LGTM",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["status"] == "approve"
        assert body["message"] == "LGTM"
