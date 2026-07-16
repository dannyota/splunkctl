"""Tests for soar workbook-templates — writes: create, update, delete."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"

_TEMPLATES: dict[str, Any] = {
    "count": 2,
    "num_pages": 1,
    "data": [
        {
            "id": 1,
            "name": "NIST 800-61",
            "is_default": True,
            "phases": [
                {"id": 10, "name": "Detection", "order": 1},
                {"id": 11, "name": "Analysis", "order": 2},
            ],
        },
        {
            "id": 2,
            "name": "Custom Investigation",
            "is_default": False,
            "phases": [
                {"id": 20, "name": "Triage", "order": 1},
            ],
        },
    ],
}


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesCreate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_success(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"id": 5, "name": "IR Workflow"}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "create",
                "--name",
                "IR Workflow",
                "--phases",
                "Detect,Contain,Recover",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["name"] == "IR Workflow"
        assert len(body["phases"]) == 3
        assert body["phases"][0]["name"] == "Detect"
        assert body["phases"][0]["order"] == 1
        assert body["phases"][2]["name"] == "Recover"
        assert body["phases"][2]["order"] == 3

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "workbook-templates",
                "create",
                "--name",
                "Test",
                "--phases",
                "A,B",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_empty_phases(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "create",
                "--name",
                "Empty",
                "--phases",
                ",,,",
            ],
        )
        assert result.exit_code != 0

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "duplicate name", kind="conflict", http_status=409
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "workbook-templates",
                "create",
                "--name",
                "Dup",
                "--phases",
                "A",
            ],
        )
        assert result.exit_code == 1
        assert "duplicate name" in result.stderr


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_add_phase(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        # First get: name resolution returns templates list
        # Second get: fetch current template detail
        client.get.side_effect = [
            _TEMPLATES,  # name resolution
            _TEMPLATES["data"][0],  # detail (phases order 1, 2)
        ]
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "NIST 800-61",
                "--add-phase",
                "Recovery",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        # Existing 2 phases + 1 new
        assert len(body["phases"]) == 3
        new_phase = body["phases"][-1]
        assert new_phase["name"] == "Recovery"
        assert new_phase["order"] == 3  # max(1,2) + 1

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES["data"][1]  # id=2
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "2",
                "--add-phase",
                "Eradicate",
                "--add-phase",
                "Lessons Learned",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        new_names = [p["name"] for p in body["phases"][-2:]]
        assert new_names == ["Eradicate", "Lessons Learned"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "workbook-templates",
                "update",
                "1",
                "--add-phase",
                "X",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_flags(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "workbook-templates", "update", "1"],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesDelete:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "workbook-templates", "delete", "1"],
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("workbook_template/1")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_name(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "delete",
                "Custom Investigation",
            ],
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("workbook_template/2")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "workbook-templates", "delete", "1"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.delete.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "workbook-templates", "delete", "99"],
        )
        assert result.exit_code == 1
        assert "not found" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_auth_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """DELETE requires Basic auth (workbook_template not in _TOKEN_DELETE_OK)."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "delete requires username/password credentials",
            kind="auth",
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "workbook-templates", "delete", "1"],
        )
        assert result.exit_code == 1
        assert "credentials" in result.stderr
