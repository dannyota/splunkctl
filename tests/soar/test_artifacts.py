"""Tests for soar artifacts — list and get (read operations)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


class TestArtifactsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_by_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """list --container N filters artifacts to that container."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {"id": 10, "name": "IP artifact", "container_id": 5},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "artifacts", "list", "--container", "5"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "IP artifact"
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_container") == 5

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "artifacts", "list", "--container", "99"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_requires_container(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """list without --container errors."""
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(cli, ["--json", "soar", "artifacts", "list"])
        assert result.exit_code != 0


class TestArtifactsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_basic(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        artifact: dict[str, Any] = {
            "id": 42,
            "name": "DNS lookup",
            "cef": {"sourceAddress": "1.2.3.4"},
        }
        client = MagicMock()
        client.get.return_value = artifact
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "artifacts", "get", "42"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == 42
        client.get.assert_called_once_with("artifact/42", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "artifacts", "get", "999"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# IntRange enforcement for --limit / --offset
# ---------------------------------------------------------------------------


class TestArtifactsLimitValidation:
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
