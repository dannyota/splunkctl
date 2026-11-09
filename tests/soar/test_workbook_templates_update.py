"""Tests for soar workbook-templates — update/add-phase."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"

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


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


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
# update
# ---------------------------------------------------------------------------
class TestWorkbookTemplatesUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_add_phase(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            _TEMPLATES,  # name resolution
            _PHASES,  # phases from their own endpoint
        ]
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "NIST 800-61",
                "--add-phase",
                "Recovery",
            ],
        )
        assert result.exit_code == 0
        client.get.assert_has_calls(
            [
                call("workbook_template", params={"_filter_name": '"NIST 800-61"'}),
                call(
                    "workbook_phase_template",
                    params={"_filter_template": 1, "page_size": 0},
                ),
            ]
        )
        client.post.assert_called_once_with(
            "workbook_phase_template",
            body={"template_id": 1, "name": "Recovery", "order": 8},
        )

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _PHASES
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "2",
                "--add-phase",
                "Eradicate",
                "--add-phase",
                "Lessons Learned",
            ],
        )
        assert result.exit_code == 0
        assert client.post.call_args_list == [
            call(
                "workbook_phase_template",
                body={"template_id": 2, "name": "Eradicate", "order": 8},
            ),
            call(
                "workbook_phase_template",
                body={"template_id": 2, "name": "Lessons Learned", "order": 9},
            ),
        ]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _PHASES
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "workbook-templates",
                "update",
                "1",
                "--add-phase",
                "X",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        assert "Detection" in result.stderr
        assert "Analysis" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_flags(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "workbook-templates", "update", "1"],
        )
        assert result.exit_code != 0

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_partial_failure(
        self, mock_resolve: MagicMock, mock_cls: MagicMock, mock_guard: MagicMock
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = mock_cls.return_value
        client.get.return_value = _PHASES
        client.post.side_effect = [
            {"success": True, "id": 12},
            SOARError("cannot add phase", kind="error", http_status=500),
        ]
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "1",
                "--add-phase",
                "Recovery",
                "--add-phase",
                "Review",
                "--add-phase",
                "Later",
            ],
        )
        assert result.exit_code == 1
        assert "Added phases before error: Recovery" in result.stderr
        assert "cannot add phase" in result.stderr
        assert client.post.call_args_list == [
            call(
                "workbook_phase_template",
                body={"template_id": 1, "name": "Recovery", "order": 8},
            ),
            call(
                "workbook_phase_template",
                body={"template_id": 1, "name": "Review", "order": 9},
            ),
        ]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_phase_read_failure(
        self, mock_resolve: MagicMock, mock_cls: MagicMock, mock_guard: MagicMock
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = mock_cls.return_value
        client.get.side_effect = SOARError(
            "cannot read phases", kind="error", http_status=500
        )
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "workbook-templates",
                "update",
                "1",
                "--add-phase",
                "Recovery",
            ],
        )
        assert result.exit_code == 1
        assert "cannot read phases" in result.stderr
        client.post.assert_not_called()
