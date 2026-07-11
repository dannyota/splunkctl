"""Tests for soar users commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


# ── users list ───────────────────────────────────────────────────────


class TestUsersList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "data": [{"id": 1, "username": "admin"}],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "users", "list"])
        assert result.exit_code == 0
        client.get.assert_called_once()
        call_params = client.get.call_args[1].get("params", {})
        assert "_filter_type" not in call_params

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_automation_type(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--type automation surfaces hidden system user."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "data": [{"id": 99, "username": "automation", "type": "automation"}],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "users", "list", "--type", "automation"]
        )
        assert result.exit_code == 0
        call_params = client.get.call_args[1].get("params", {})
        assert call_params["_filter_type"] == '"automation"'


# ── users get ────────────────────────────────────────────────────────


class TestUsersGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_user(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"id": 1, "username": "admin"}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "users", "get", "1"])
        assert result.exit_code == 0
        client.get.assert_called_once_with("ph_user/1")


# ── users create ─────────────────────────────────────────────────────


class TestUsersCreate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_normal(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"id": 10}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "users",
                "create",
                "--username",
                "testuser",
                "--password",
                "Passw0rd!",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["username"] == "testuser"
        assert body["type"] == "normal"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_automation_shows_token_reality(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"id": 11}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "users",
                "create",
                "--username",
                "bot",
                "--password",
                "Passw0rd!",
                "--type",
                "automation",
            ],
        )
        assert result.exit_code == 0
        assert "plaintext" in result.stderr.lower() or "token" in result.stderr.lower()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run_masks_password(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "users",
                "create",
                "--username",
                "testuser",
                "--password",
                "Secret123!",
            ],
        )
        assert result.exit_code == 0
        assert "Secret123!" not in result.output
        assert "Secret123!" not in result.stderr
        assert "********" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_roles(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"id": 12}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "users",
                "create",
                "--username",
                "u1",
                "--password",
                "P@ss1",
                "--role",
                "Analyst",
                "--role",
                "Observer",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["roles"] == ["Analyst", "Observer"]


# ── users update ─────────────────────────────────────────────────────


class TestUsersUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_password(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "users",
                "update",
                "5",
                "--password",
                "NewP@ss1",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["password"] == "NewP@ss1"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_add_remove_roles(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Read-modify-write merges roles correctly."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            # fetch current user roles
            {"id": 5, "roles": [1, 2]},
            # fetch role list for name→id resolution (add)
            {
                "data": [
                    {"id": 1, "name": "Admin"},
                    {"id": 2, "name": "Analyst"},
                    {"id": 3, "name": "Observer"},
                ]
            },
            # fetch role list for name→id resolution (remove)
            {
                "data": [
                    {"id": 1, "name": "Admin"},
                    {"id": 2, "name": "Analyst"},
                    {"id": 3, "name": "Observer"},
                ]
            },
        ]
        client.post.return_value = {"success": True}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "users",
                "update",
                "5",
                "--add-role",
                "Observer",
                "--remove-role",
                "Admin",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert 3 in body["roles"]  # Observer added
        assert 1 not in body["roles"]  # Admin removed
        assert 2 in body["roles"]  # Analyst kept

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_flags_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        result = CliRunner().invoke(
            cli, ["--yes", "--json", "soar", "users", "update", "5"]
        )
        assert result.exit_code == 1


# ── users delete ─────────────────────────────────────────────────────


class TestUsersDelete:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_user(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--yes", "soar", "users", "delete", "5"])
        assert result.exit_code == 0
        assert "soft-deleted" in result.stderr.lower()
        client.delete.assert_called_once_with("ph_user/5")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run_explains_soft_delete(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _guard_cfg()
        result = CliRunner().invoke(cli, ["soar", "users", "delete", "5"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr
        assert "soft delete" in result.stderr.lower()


# ── users token ──────────────────────────────────────────────────────


class TestUsersToken:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_token_shows_hashed_key(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "key": "abc123hash",
            "expires_on": "2027-01-01",
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "users", "token", "5"])
        assert result.exit_code == 0
        client.get.assert_called_once_with("ph_user/5/token")
