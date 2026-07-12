"""Tests for soar cases task update — closing-note handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
_GUARD = "splunkctl.guard.cfg_mod.resolve_soar"


def _guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(cli, args)


class TestTaskUpdateNotes:
    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_status_note_sent_inline(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """--status with --note carries the note INLINE in the task POST.

        A separate note POST arrives too late — the server rejects
        note-requiring transitions without an inline ``note`` field.
        """
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.get.return_value = {"id": 100, "container": 42}
        client.post.return_value = {"success": True}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "task",
                "update",
                "100",
                "--status",
                "in_progress",
                "--note",
                "Starting investigation",
            ]
        )
        assert r.exit_code == 0
        assert client.post.call_count == 1
        path = client.post.call_args_list[0][0][0]
        body = client.post.call_args_list[0][1]["body"]
        assert path == "workbook_task/100"
        assert body["status"] == 1
        assert body["note"] == "Starting investigation"

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_note_without_status_posts_standalone(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """--note alone still posts a task-linked note to /rest/note."""
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.get.return_value = {"id": 100, "container": 42}
        client.post.return_value = {"success": True}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "task",
                "update",
                "100",
                "--note",
                "Progress update",
            ]
        )
        assert r.exit_code == 0
        assert client.post.call_count == 1
        path = client.post.call_args_list[0][0][0]
        body = client.post.call_args_list[0][1]["body"]
        assert path == "note"
        assert body["content"] == "Progress update"
        assert body["task_id"] == 100
