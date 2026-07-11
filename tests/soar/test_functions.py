"""Tests for soar functions — list, get (read-side)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


# ---------------------------------------------------------------------------
# Functions list
# ---------------------------------------------------------------------------
class TestFunctionsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Bare list returns custom functions."""
        mock_resolve.return_value = soar_cfg()
        items: dict[str, Any] = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "format_ip", "module": "format_ip"},
                {"id": 2, "name": "lookup_hash", "module": "lookup_hash"},
            ],
        }
        client = MagicMock()
        client.get.return_value = items
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "functions", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "format_ip"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Empty list renders correctly."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "functions", "list"])
        assert result.exit_code == 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """API error exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth", http_status=401)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "functions", "list"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Functions get
# ---------------------------------------------------------------------------
class TestFunctionsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_id(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Get a custom function by numeric ID."""
        mock_resolve.return_value = soar_cfg()
        item: dict[str, Any] = {
            "id": 42,
            "name": "format_ip",
            "python": "def main():\n    pass\n",
            "module": "format_ip",
        }
        client = MagicMock()
        client.get.return_value = item
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "functions", "get", "42"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == 42

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """404 exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "functions", "get", "999"])
        assert result.exit_code != 0
