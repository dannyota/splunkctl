"""Tests for soar lists — writes: create, update, add/remove-row, delete, import."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_GUARD = "splunkctl.commands.soar.lists.soar_check"


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
class TestListsCreate:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = False
        client = MagicMock()
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["soar", "lists", "create", "--name", "test"])
        assert result.exit_code == 0
        client.post.assert_not_called()

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_empty(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        """Create with no --file makes an empty list."""
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 10}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "lists", "create", "--name", "test"],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["name"] == "test"
        assert body["content"] == []

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_from_json(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 11}
        mock_cls.return_value = client

        f = tmp_path / "rows.json"
        f.write_text(json.dumps([["a", "b"], ["c", "d"]]))

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "create",
                "--name",
                "t",
                "--file",
                str(f),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == [["a", "b"], ["c", "d"]]

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_from_csv(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 12}
        mock_cls.return_value = client

        f = tmp_path / "rows.csv"
        f.write_text("col1,col2\na,b\nc,d\n")

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "create",
                "--name",
                "t",
                "--file",
                str(f),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == [
            ["col1", "col2"],
            ["a", "b"],
            ["c", "d"],
        ]


# ---------------------------------------------------------------------------
# update (full-replace)
# ---------------------------------------------------------------------------
class TestListsUpdate:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_full_replace(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        f = tmp_path / "new.json"
        f.write_text(json.dumps([["x", "y"]]))

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "update",
                "1",
                "--file",
                str(f),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == [["x", "y"]]

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = False
        client = MagicMock()
        mock_cls.return_value = client

        f = tmp_path / "new.json"
        f.write_text(json.dumps([["x"]]))

        result = CliRunner().invoke(
            cli, ["soar", "lists", "update", "1", "--file", str(f)]
        )
        assert result.exit_code == 0
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# add-row / remove-row
# ---------------------------------------------------------------------------
class TestListsAddRow:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_row(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "blocklist",
            "content": [["h1"], ["a"]],
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "add-row",
                "1",
                "--values",
                "b",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == [["h1"], ["a"], ["b"]]

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_row_multiple_values(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "test",
            "content": [["c1", "c2"]],
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "add-row",
                "1",
                "--values",
                "x,y",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == [["c1", "c2"], ["x", "y"]]


class TestListsRemoveRow:
    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_remove_row_by_index(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "blocklist",
            "content": [["h1"], ["a"], ["b"], ["c"]],
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "remove-row",
                "1",
                "--index",
                "1",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        # Row at index 1 ("a") removed; header + remaining.
        assert body["content"] == [["h1"], ["b"], ["c"]]

    @patch(PATCH_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_remove_row_index_out_of_range(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        mock_g: MagicMock,
    ) -> None:
        mock_res.return_value = soar_cfg()
        mock_g.return_value = True
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "test",
            "content": [["h1"], ["a"]],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "lists",
                "remove-row",
                "1",
                "--index",
                "99",
            ],
        )
        assert result.exit_code != 0


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
    def test_delete_applies(
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
