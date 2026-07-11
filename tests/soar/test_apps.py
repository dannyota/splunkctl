"""Tests for soar apps — list and get (read operations)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


def _app(
    app_id: int = 1,
    name: str = "DNS",
    *,
    install_status: str = "installed",
) -> dict[str, Any]:
    return {
        "id": app_id,
        "name": name,
        "install_status": install_status,
        "category": "Information",
    }


class TestAppsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_all(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [_app(1, "DNS"), _app(2, "VirusTotal")],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "apps", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_installed(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """--installed adds _exclude_install_status=staged."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_app(1, "DNS")],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "apps", "list", "--installed"]
        )
        assert result.exit_code == 0
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_exclude_install_status") == '"staged"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_category(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "apps", "list", "--category", "SIEM"]
        )
        assert result.exit_code == 0
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_category") == '"SIEM"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth", http_status=401)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "apps", "list"])
        assert result.exit_code == 1


class TestAppsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_basic(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        app: dict[str, Any] = {
            "id": 5,
            "name": "DNS",
            "configuration": {
                "dns_server": {
                    "data_type": "string",
                    "required": True,
                    "default": "8.8.8.8",
                }
            },
        }
        client = MagicMock()
        client.get.return_value = app
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "apps", "get", "5"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "DNS"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_with_actions(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--actions appends the app's supported actions."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"id": 5, "name": "DNS", "configuration": {}},
            {
                "count": 1,
                "num_pages": 1,
                "data": [{"action": "lookup domain", "type": "investigate"}],
            },
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "apps", "get", "5", "--actions"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "DNS"
        assert "actions" in data[0]
        assert data[0]["actions"][0]["action"] == "lookup domain"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "apps", "get", "999"])
        assert result.exit_code == 1
