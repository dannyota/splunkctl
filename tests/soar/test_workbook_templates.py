"""Tests for soar workbook-templates — reads: list, get."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

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


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "list"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "NIST 800-61"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_limit(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_TEMPLATES["data"][0]],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "workbook-templates", "list", "--limit", "1"],
        )
        assert result.exit_code == 0
        # Verify page_size param was passed
        call_kwargs = client.get.call_args
        params = call_kwargs[1].get("params", {})
        assert params.get("page_size") == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth", http_status=401)
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "list"]
        )
        assert result.exit_code != 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["soar", "workbook-templates", "list"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_id(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES["data"][0]
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "get", "1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "NIST 800-61"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_name(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        """Non-numeric argument triggers name lookup then detail fetch."""
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = [
            _TEMPLATES,  # name resolution
            _TEMPLATES["data"][0],  # detail fetch
        ]
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "get", "NIST 800-61"]
        )
        assert result.exit_code == 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_name_not_found(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "workbook-templates", "get", "nonexistent"],
        )
        assert result.exit_code != 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_api_error(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "server error", kind="error", http_status=500
        )
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "get", "1"]
        )
        assert result.exit_code != 0
