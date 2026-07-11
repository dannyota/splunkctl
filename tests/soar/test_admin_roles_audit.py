"""Tests for soar roles and audit commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

# ── roles ────────────────────────────────────────────────────────────


class TestRolesList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_roles(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "data": [
                {"id": 1, "name": "Administrator"},
                {"id": 2, "name": "Analyst"},
            ],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "roles", "list"])
        assert result.exit_code == 0


class TestRolesGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_role(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "Administrator",
            "permissions": {"admin": True},
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "roles", "get", "1"])
        assert result.exit_code == 0
        client.get.assert_called_once_with("role/1")


# ── audit ────────────────────────────────────────────────────────────


class TestAudit:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "message": "login", "username": "admin"},
                {"id": 2, "message": "logout", "username": "admin"},
            ],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "audit"])
        assert result.exit_code == 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_with_filters(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "audit",
                "--user",
                "admin",
                "--start",
                "2026-01-01",
                "--end",
                "2026-12-31",
            ],
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["_filter_username__icontains"] == '"admin"'
        assert params["start"] == "2026-01-01"
        assert params["end"] == "2026-12-31"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_csv_format(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "audit", "--format", "csv"])
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["format"] == "csv"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_container_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "audit", "--container", "42"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["_filter_container"] == "42"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth")
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "audit"])
        assert result.exit_code == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_playbook_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "audit", "--playbook", "my_playbook"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["_filter_playbook__icontains"] == '"my_playbook"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_audit_limit(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "audit", "--limit", "10"])
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page_size"] == 10
