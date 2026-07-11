"""Tests for Phase M branch review fixes.

Covers: --limit 0 IntRange, SDI precheck error warnings, @guarded
decorator visibility, and _extract_payload [] fallback.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.commands.soar.containers import _extract_payload
from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


# ---------------------------------------------------------------------------
# Item 1: --limit 0 exits 2 (IntRange enforcement)
# ---------------------------------------------------------------------------


class TestLimitZeroContainers:
    def test_limit_zero_exits_2(self) -> None:
        """--limit 0 is rejected by Click IntRange(min=1)."""
        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--limit", "0"]
        )
        assert result.exit_code == 2

    def test_negative_limit_exits_2(self) -> None:
        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--limit", "-1"]
        )
        assert result.exit_code == 2

    def test_negative_offset_exits_2(self) -> None:
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "containers",
                "list",
                "--limit",
                "5",
                "--offset",
                "-1",
            ],
        )
        assert result.exit_code == 2


class TestLimitZeroArtifacts:
    def test_limit_zero_exits_2(self) -> None:
        """--limit 0 is rejected by Click IntRange(min=1)."""
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "artifacts",
                "list",
                "--container",
                "1",
                "--limit",
                "0",
            ],
        )
        assert result.exit_code == 2

    def test_negative_offset_exits_2(self) -> None:
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "artifacts",
                "list",
                "--container",
                "1",
                "--limit",
                "5",
                "--offset",
                "-1",
            ],
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Item 3: SDI precheck failure emits warning instead of silence
# ---------------------------------------------------------------------------


class TestSdiPrecheckWarning:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_container_sdi_precheck_failure_warns(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Container create: SDI precheck SOARError emits warning, create proceeds."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("timeout", kind="timeout", http_status=504)
        client.post.return_value = {"success": True, "id": 99}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "create",
                "--name",
                "test",
                "--label",
                "events",
                "--sdi",
                "SDI-fail",
            ],
        )
        assert result.exit_code == 0
        assert "could not verify SDI uniqueness" in result.stderr
        assert "timeout" in result.stderr
        client.post.assert_called_once()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_artifact_sdi_precheck_failure_warns(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Artifact create: SDI precheck SOARError emits warning, create proceeds."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("server error", kind="http", http_status=500)
        client.post.return_value = {"success": True, "id": 88}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Test",
                "--sdi",
                "SDI-fail",
            ],
        )
        assert result.exit_code == 0
        assert "could not verify SDI uniqueness" in result.stderr
        assert "server error" in result.stderr
        client.post.assert_called_once()


# ---------------------------------------------------------------------------
# Item 4: _extract_payload [] fallback
# ---------------------------------------------------------------------------


class TestExtractPayloadFallback:
    def test_non_dict_non_list_sub_view_returns_list(self) -> None:
        """Non-dict, non-list result with a sub_view returns [] (not {})."""
        result = _extract_payload("unexpected string", "artifacts")
        assert result == []
        assert isinstance(result, list)

    def test_sub_view_data_non_standard_returns_list(self) -> None:
        """data key with non-list/non-dict inner returns []."""
        result = _extract_payload({"data": "string_value"}, "notes")
        assert result == []
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Item 5 & 6: @guarded visibility in commands --json
# ---------------------------------------------------------------------------


class TestGuardedMarkers:
    def test_vault_upload_guarded(self) -> None:
        """vault upload reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        guarded = _collect_guarded(data["commands"])
        assert "upload" in guarded, "vault upload should be guarded"

    def test_vault_delete_guarded(self) -> None:
        """vault delete reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        guarded = _collect_guarded(data["commands"])
        assert "delete" in guarded, "vault delete should be guarded"

    def test_notes_add_guarded(self) -> None:
        """notes add reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.add" in soar_cmds, "notes add should be guarded"

    def test_notes_delete_guarded(self) -> None:
        """notes delete reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.delete" in soar_cmds, "notes delete should be guarded"

    def test_notes_comment_guarded(self) -> None:
        """notes comment reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.comment" in soar_cmds, "notes comment should be guarded"


def _collect_guarded(nodes: list[dict[str, Any]]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for n in nodes:
        if "subcommands" in n:
            out.update(_collect_guarded(n["subcommands"]))
        elif n.get("guarded"):
            out[str(n["name"])] = True
    return out


def _collect_guarded_full_path(
    nodes: list[dict[str, Any]],
    prefix: str = "",
) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for n in nodes:
        path = f"{prefix}.{n['name']}" if prefix else str(n["name"])
        if "subcommands" in n:
            out.update(_collect_guarded_full_path(n["subcommands"], path))
        elif n.get("guarded"):
            out[path] = True
    return out
