"""Tests for soar cases — phase add, task add, task update."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
_GUARD = "splunkctl.guard.cfg_mod.resolve_soar"


def _guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(cli, args)


class TestPhaseAdd:
    """phase add --container --name [--order]."""

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_phase_add(self, mr: MagicMock, mc: MagicMock, mg: MagicMock) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 55}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "phase",
                "add",
                "--container",
                "42",
                "--name",
                "Recovery",
            ]
        )
        assert r.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["container_id"] == 42
        assert body["name"] == "Recovery"
        assert "order" not in body

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_phase_add_with_order(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 56}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "phase",
                "add",
                "--container",
                "42",
                "--name",
                "Recovery",
                "--order",
                "3",
            ]
        )
        assert r.exit_code == 0
        assert client.post.call_args[1]["body"]["order"] == 3

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_phase_add_dry_run(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(
            ["soar", "cases", "phase", "add", "--container", "42", "--name", "Recovery"]
        )
        assert r.exit_code == 0
        assert "[DRY RUN]" in r.stderr
        mc.return_value.post.assert_not_called()


class TestTaskAdd:
    """task add --phase-id --name [--description --order]."""

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_task_add(self, mr: MagicMock, mc: MagicMock, mg: MagicMock) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 200}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "task",
                "add",
                "--phase-id",
                "10",
                "--name",
                "Review logs",
            ]
        )
        assert r.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["phase_id"] == 10
        assert body["name"] == "Review logs"

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_task_add_with_options(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 201}
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "soar",
                "cases",
                "task",
                "add",
                "--phase-id",
                "10",
                "--name",
                "Review logs",
                "--description",
                "Check all logs",
                "--order",
                "5",
            ]
        )
        assert r.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["description"] == "Check all logs"
        assert body["order"] == 5

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_task_add_dry_run(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(
            [
                "soar",
                "cases",
                "task",
                "add",
                "--phase-id",
                "10",
                "--name",
                "Review logs",
            ]
        )
        assert r.exit_code == 0
        assert "[DRY RUN]" in r.stderr


class TestTaskUpdate:
    """task update <id> [--status --owner --note]."""

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_status_complete(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """0 -> 2 (complete) allowed without a note."""
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mc.return_value = client

        r = _run(
            ["--yes", "soar", "cases", "task", "update", "100", "--status", "complete"]
        )
        assert r.exit_code == 0
        assert client.post.call_args[1]["body"]["status"] == 2

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_in_progress_requires_note(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """in_progress transition requires --note (client-side)."""
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(
            [
                "--yes",
                "--json",
                "soar",
                "cases",
                "task",
                "update",
                "100",
                "--status",
                "in_progress",
            ]
        )
        assert r.exit_code == 1
        assert "closing note" in r.stderr.lower()

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_in_progress_with_note(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """in_progress with --note succeeds."""
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
                "Starting",
            ]
        )
        assert r.exit_code == 0
        assert client.post.call_args_list[0][1]["body"]["status"] == 1

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_owner(self, mr: MagicMock, mc: MagicMock, mg: MagicMock) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mc.return_value = client

        r = _run(
            ["--yes", "soar", "cases", "task", "update", "100", "--owner", "analyst"]
        )
        assert r.exit_code == 0
        assert client.post.call_args[1]["body"]["owner"] == "analyst"

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_invalid_status(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(
            [
                "--yes",
                "--json",
                "soar",
                "cases",
                "task",
                "update",
                "100",
                "--status",
                "bogus",
            ]
        )
        assert r.exit_code != 0

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_no_flags_errors(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(["--yes", "--json", "soar", "cases", "task", "update", "100"])
        assert r.exit_code == 1

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        mc.return_value = MagicMock()

        r = _run(["soar", "cases", "task", "update", "100", "--status", "complete"])
        assert r.exit_code == 0
        assert "[DRY RUN]" in r.stderr

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_status_incomplete(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        """incomplete (0) does not require a note."""
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
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
                "incomplete",
            ]
        )
        assert r.exit_code == 0
        assert client.post.call_args[1]["body"]["status"] == 0

    @patch(_GUARD)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_server_error(
        self,
        mr: MagicMock,
        mc: MagicMock,
        mg: MagicMock,
    ) -> None:
        mr.return_value = _CFG
        mg.return_value = _guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError("not found", kind="not_found")
        mc.return_value = client

        r = _run(
            [
                "--yes",
                "--json",
                "soar",
                "cases",
                "task",
                "update",
                "100",
                "--status",
                "complete",
            ]
        )
        assert r.exit_code == 1
        assert "not found" in r.stderr
