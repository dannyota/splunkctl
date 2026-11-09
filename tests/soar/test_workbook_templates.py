"""Tests for soar workbook-templates — reads: list, get."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

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
        },
        {
            "id": 2,
            "name": "Custom Investigation",
            "is_default": False,
        },
    ],
}


_PHASES: dict[str, Any] = {
    "count": 2,
    "num_pages": 1,
    "data": [
        {
            "create_time": "2026-11-09T00:00:00Z",
            "id": 10,
            "modified_time": "2026-11-09T00:00:00Z",
            "name": "Detection",
            "order": 7,
            "sla": 0,
            "sla_type": "minutes",
            "template": 1,
            "tasks": [
                {
                    "create_time": "2026-11-09T00:00:00Z",
                    "description": "Keep this task",
                    "id": 100,
                    "is_note_required": True,
                    "modified_time": "2026-11-09T00:00:00Z",
                    "name": "Investigate",
                    "order": 1,
                    "owner": None,
                    "phase": 10,
                    "role": None,
                    "sla": 0,
                    "sla_type": "minutes",
                    "suggestions": [],
                }
            ],
        },
        {
            "create_time": "2026-11-09T00:00:00Z",
            "id": 11,
            "modified_time": "2026-11-09T00:00:00Z",
            "name": "Analysis",
            "order": 2,
            "sla": 0,
            "sla_type": "minutes",
            "tasks": [],
            "template": 1,
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
        client.get.side_effect = [_TEMPLATES["data"][0], _PHASES]
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "get", "1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "NIST 800-61"
        assert data[0]["phases"] == _PHASES["data"]
        client.get.assert_has_calls(
            [
                call("workbook_template/1", params={}),
                call(
                    "workbook_phase_template",
                    params={"_filter_template": 1, "page_size": 0},
                ),
            ]
        )

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_name(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        """Non-numeric argument triggers name lookup then detail fetch."""
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = [
            _TEMPLATES,  # name resolution
            _TEMPLATES["data"][0],  # detail fetch
            _PHASES,
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

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_phase_read_failure_warns(
        self, mock_res: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_res.return_value = soar_cfg()
        client = mock_cls.return_value
        client.get.side_effect = [
            _TEMPLATES["data"][0],
            SOARError("cannot read phases", kind="error", http_status=500),
        ]
        result = CliRunner().invoke(
            cli, ["--json", "soar", "workbook-templates", "get", "1"]
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout) == [_TEMPLATES["data"][0]]
        assert "cannot read phases" in result.stderr
