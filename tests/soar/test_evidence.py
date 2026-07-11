"""Tests for soar evidence commands — list, add (guarded), remove (guarded)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


class TestEvidenceList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_by_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        evidence_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {
                    "id": 5,
                    "container_id": 100,
                    "object_type": "artifact",
                    "object_id": 42,
                }
            ],
        }
        client = MagicMock()
        client.get.return_value = evidence_resp
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "evidence", "list", "--container", "100"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["object_type"] == "artifact"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_passes_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Verify _filter_container is sent in the query params."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            ["--json", "soar", "evidence", "list", "--container", "42"],
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params["_filter_container"] == 42

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "evidence", "list", "--container", "999"],
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_requires_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(cli, ["--json", "soar", "evidence", "list"])
        assert result.exit_code != 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("boom", kind="http", http_status=500)
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "evidence", "list", "--container", "1"],
        )
        assert result.exit_code == 1


class TestEvidenceAdd:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_dry_run(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Without --yes, add previews and exits 0."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "evidence",
                "add",
                "100",
                "--object",
                "artifact",
                "--id",
                "42",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_with_yes(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 77}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "evidence",
                "add",
                "100",
                "--object",
                "artifact",
                "--id",
                "42",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "evidence"
        body = call_args[1]["body"]
        assert body["container_id"] == 100
        assert body["object_type"] == "artifact"
        assert body["object_id"] == 42
        assert "Evidence added: id=77" in result.stderr

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_action_run(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """action_run is a valid object type."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 88}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "evidence",
                "add",
                "50",
                "--object",
                "action_run",
                "--id",
                "7",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["object_type"] == "action_run"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_add_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "conflict", kind="conflict", http_status=409
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "evidence",
                "add",
                "100",
                "--object",
                "note",
                "--id",
                "5",
            ],
        )
        assert result.exit_code == 1


class TestEvidenceRemove:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_remove_dry_run(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "evidence", "remove", "5"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.delete.assert_not_called()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_remove_with_yes(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "evidence", "remove", "5"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("evidence/5")
        assert "Evidence 5 removed" in result.stderr

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_remove_api_error(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "evidence", "remove", "999"]
        )
        assert result.exit_code == 1
