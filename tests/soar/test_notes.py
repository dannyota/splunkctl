"""Tests for soar notes — list, add, delete, and comments."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_BANNER = "splunkctl.guard.banner_soar"


# ---------------------------------------------------------------------------
# notes list
# ---------------------------------------------------------------------------


class TestNotesList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_by_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """List notes for a container via GET /rest/container/<id>/notes."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 10, "title": "Summary", "note_type": "general"},
                {"id": 11, "title": "Task note", "note_type": "task"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "notes", "list", "--container", "1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["title"] == "Summary"
        client.get.assert_called_once()
        path_arg = client.get.call_args[0][0]
        assert path_arg == "container/1/notes"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_task_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--task filters by task_id in the params."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 1, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "notes",
                "list",
                "--container",
                "5",
                "--task",
                "42",
            ],
        )
        call_args = client.get.call_args
        path_arg = call_args[0][0]
        assert path_arg == "note"
        params = call_args[1].get("params", {})
        assert params.get("_filter_task_id") == 42
        assert params.get("_filter_container") == 5

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_container_required(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Missing --container is a usage error."""
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(cli, ["--json", "soar", "notes", "list"])
        assert result.exit_code != 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "notes", "list", "--container", "1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "notes", "list", "--container", "999"]
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# notes add
# ---------------------------------------------------------------------------


class TestNotesAdd:
    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """Default (no --yes) prints dry-run preview, does NOT post."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--title",
                "Summary",
                "This is the content",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """--yes posts the note to the API."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 99}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--title",
                "Summary",
                "markdown content here",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        call_kwargs = client.post.call_args[1]
        body = call_kwargs["body"]
        assert body["container_id"] == 1
        assert body["title"] == "Summary"
        assert body["content"] == "markdown content here"
        assert body["note_type"] == "general"

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_task_note(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """--task-id makes it a task note."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 100}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--task-id",
                "5",
                "--title",
                "Task analysis",
                "Task body",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["task_id"] == 5
        assert body["note_type"] == "task"

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_from_file(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
        tmp_path: Any,
    ) -> None:
        """--file reads content from a file."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 101}
        mock_cls.return_value = client

        content_file = tmp_path / "note.md"
        content_file.write_text("# Investigation\n\nFound IOCs.")

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--title",
                "File note",
                "--file",
                str(content_file),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["content"] == "# Investigation\n\nFound IOCs."

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_no_content_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """No content arg and no --file is a usage error."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--title",
                "Empty",
            ],
        )
        assert result.exit_code == 1

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """API error on post exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError("bad request", kind="http", http_status=400)
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "add",
                "--container",
                "1",
                "--title",
                "Fail",
                "content",
            ],
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# notes delete
# ---------------------------------------------------------------------------


class TestNotesDelete:
    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """Default (no --yes) prints dry-run, does NOT delete."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "notes", "delete", "10"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr
        client.delete.assert_not_called()

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        """--yes deletes the note."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.return_value = {"id": 10}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "notes", "delete", "10"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("note/10")

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "auth required", kind="auth", http_status=401
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "notes", "delete", "10"]
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# comment add
# ---------------------------------------------------------------------------


class TestCommentAdd:
    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_comment_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "notes", "comment", "1", "my comment"]
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_comment_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 50}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "notes",
                "comment",
                "1",
                "Investigation complete",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["container_id"] == 1
        assert body["comment"] == "Investigation complete"

    @patch(PATCH_BANNER, return_value="(SOAR @ soar.test:8443)")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_comment_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _banner: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError("bad", kind="http", http_status=400)
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "notes", "comment", "1", "text"],
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# comment delete — immutability guard
# ---------------------------------------------------------------------------


class TestCommentDeleteImmutable:
    def test_comment_delete_explains_immutability(self) -> None:
        """Attempting to delete a comment returns a clear immutability message."""
        result = CliRunner().invoke(
            cli, ["--json", "soar", "notes", "comment-delete", "50"]
        )
        assert result.exit_code == 1
        assert "immutable" in result.stderr.lower() or "cannot" in result.stderr.lower()
