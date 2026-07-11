"""Tests for soar cases — promote and workbook commands."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"

# -- Workbook template fixtures --

_TEMPLATES: dict[str, Any] = {
    "count": 2,
    "data": [
        {"id": 1, "name": "NIST 800-61", "is_default": True},
        {"id": 2, "name": "Custom Investigation", "is_default": False},
    ],
}

# -- Phase/task fixtures for workbook view --

_PHASES_RESP: dict[str, Any] = {
    "count": 2,
    "data": [
        {
            "id": 10,
            "name": "Detection",
            "order": 1,
            "tasks": [
                {"id": 100, "name": "Identify IOCs", "status": 0, "owner": None},
                {"id": 101, "name": "Validate alert", "status": 2, "owner": "admin"},
            ],
        },
        {
            "id": 11,
            "name": "Containment",
            "order": 2,
            "tasks": [
                {"id": 102, "name": "Isolate host", "status": 1, "owner": "analyst"},
            ],
        },
    ],
}


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


class TestPromote:
    """promote <id> [--template <name|id>]."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_default_template(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Promote with no --template uses the is_default template."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = lambda path, **kw: (
            _TEMPLATES if path == "workbook_template" else {}
        )
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "cases", "promote", "42"],
        )
        assert result.exit_code == 0
        client.post.assert_called_once_with(
            "container/42",
            body={"container_type": "case", "template": 1},
        )

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_by_template_name(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """--template resolves name to id."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = lambda path, **kw: (
            _TEMPLATES if path == "workbook_template" else {}
        )
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "cases",
                "promote",
                "42",
                "--template",
                "Custom Investigation",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["template"] == 2

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_by_template_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """--template accepts a numeric id directly."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "cases", "promote", "42", "--template", "2"],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["template"] == 2

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_unknown_template(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "cases",
                "promote",
                "42",
                "--template",
                "Nonexistent",
            ],
        )
        assert result.exit_code == 1
        assert "Nonexistent" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "cases", "promote", "42"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_server_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = _TEMPLATES
        client.post.side_effect = SOARError("already a case", kind="conflict")
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "cases", "promote", "42"],
        )
        assert result.exit_code == 1
        assert "already a case" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_promote_no_default_template(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """When no template has is_default, error with available names."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        no_default = {
            "data": [
                {"id": 1, "name": "Custom A", "is_default": False},
                {"id": 2, "name": "Custom B", "is_default": False},
            ],
        }
        client.get.return_value = no_default
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "cases", "promote", "42"],
        )
        assert result.exit_code == 1
        assert "no default" in result.stderr.lower()


class TestWorkbook:
    """workbook <container> -- phases + nested tasks view."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_workbook_view(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        client = MagicMock()
        client.get.return_value = _PHASES_RESP
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "cases", "workbook", "42"],
        )
        assert result.exit_code == 0
        client.get.assert_called_once()
        call_path = client.get.call_args[0][0]
        assert call_path == "container/42/phases"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_workbook_empty(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        client = MagicMock()
        client.get.return_value = {"data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "cases", "workbook", "42"],
        )
        assert result.exit_code == 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_workbook_json_output(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        client = MagicMock()
        client.get.return_value = _PHASES_RESP
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "cases", "workbook", "42"],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
