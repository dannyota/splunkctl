"""Tests for soar lists — delete and import commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_GUARD = "splunkctl.commands.soar.lists.soar_check"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
class TestListsDelete:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = False
        client = MagicMock()
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["soar", "lists", "delete", "1"])
        assert result.exit_code == 0
        client.delete.assert_not_called()

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_applies_by_id(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.delete.return_value = {"success": True}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--yes", "soar", "lists", "delete", "1"])
        assert result.exit_code == 0
        client.delete.assert_called_once_with("decided_list/1")

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_name(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        """delete resolves a name to id via _resolve_list_id."""
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 7, "name": "blocklist"}],
        }
        client.delete.return_value = {"success": True}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--yes", "soar", "lists", "delete", "blocklist"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("decided_list/7")


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
class TestListsImport:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_creates_new(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        client.post.return_value = {"success": True, "id": 20}
        mock_cls.return_value = client

        f = tmp_path / "rows.json"
        f.write_text(json.dumps([["x", "y"]]))

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "import",
                "--name",
                "new",
                "--file",
                str(f),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["name"] == "new"
        assert body["content"] == [["x", "y"]]

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_updates_existing(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 5, "name": "existing"}],
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        f = tmp_path / "rows.csv"
        f.write_text("c1\na\nb\n")

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "import",
                "--name",
                "existing",
                "--file",
                str(f),
            ],
        )
        assert result.exit_code == 0
        # Should POST to decided_list/5 (update).
        call_path = client.post.call_args[0][0]
        assert call_path == "decided_list/5"
