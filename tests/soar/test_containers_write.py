"""Tests for soar containers update, close, assign, delete."""

from __future__ import annotations

import json
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


class TestContainerUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_single(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Update a single container."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "42",
                "--severity",
                "critical",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container/42"
        body = client.post.call_args[1]["body"]
        assert body["severity"] == "critical"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_status_numeric_rejected(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Numeric status id is rejected with a usage error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "update",
                "42",
                "--status",
                "2",
            ],
        )
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"
        assert "numeric id" in payload["error"]["message"]
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_changes_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Update with no setters exits 1."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "containers", "update", "42"],
        )
        assert result.exit_code == 1

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_bulk(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Bulk update posts array to /rest/container."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "1",
                "2",
                "3",
                "--severity",
                "low",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container"
        body = client.post.call_args[1]["body"]
        assert isinstance(body, list)
        assert len(body) == 3
        assert body[0]["id"] == 1
        assert body[2]["id"] == 3
        assert all(item["severity"] == "low" for item in body)

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_with_tags_read_modify_write(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Tags merge existing + new via read-modify-write."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"id": 42, "tags": ["existing"]}
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "42",
                "--tag",
                "new_tag",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["tags"] == ["existing", "new_tag"]


class TestContainerClose:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_close_single(
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
            ["--yes", "soar", "containers", "close", "42"],
        )
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "container/42",
            body={"status": "closed"},
        )

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_close_bulk_single_post(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Bulk close sends one array POST."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "close", "1", "2", "3"],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container"
        body = client.post.call_args[1]["body"]
        assert isinstance(body, list)
        assert len(body) == 3
        assert all(item["status"] == "closed" for item in body)
        assert [item["id"] for item in body] == [1, 2, 3]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_close_dry_run(
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
            ["soar", "containers", "close", "42"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()


class TestContainerAssign:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_assign_owner(
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
            ["--yes", "soar", "containers", "assign", "42", "--owner", "analyst"],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["owner_name"] == "analyst"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_assign_no_flags_errors(
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
            ["--yes", "--json", "soar", "containers", "assign", "42"],
        )
        assert result.exit_code == 1

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_assign_bulk(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "assign",
                "1",
                "2",
                "--owner",
                "admin",
                "--role",
                "analyst",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert isinstance(body, list)
        assert len(body) == 2


class TestContainerDelete:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_single(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "delete", "42"],
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("container/42")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_multiple(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "delete", "1", "2", "3"],
        )
        assert result.exit_code == 0
        assert client.delete.call_count == 3
        client.delete.assert_any_call("container/1")
        client.delete.assert_any_call("container/2")
        client.delete.assert_any_call("container/3")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_auth_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Delete with token-only creds surfaces auth error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "delete requires username/password credentials",
            kind="auth",
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "containers", "delete", "42"],
        )
        assert result.exit_code == 1
        assert "username/password" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
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
            ["soar", "containers", "delete", "42"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.delete.assert_not_called()
