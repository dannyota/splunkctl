"""Tests for soar admin visibility — settings, stats, meta."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, mock_client, soar_cfg

# -------------------------------------------------------------------
# soar settings
# -------------------------------------------------------------------


class TestSoarSettings:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_all_sections(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        settings_data: dict[str, Any] = {
            "auth_settings": {"idle_timeout": 60},
            "response_settings": {"default_sla": 30},
            "debug_settings": {"actiond_debug_level": 1},
        }
        client = mock_client({"system_settings": settings_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "settings"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        sections = [r["section"] for r in data]
        assert "auth_settings" in sections

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_filter_section(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        settings_data: dict[str, Any] = {
            "auth_settings": {"idle_timeout": 60},
            "response_settings": {"default_sla": 30},
        }
        client = mock_client({"system_settings": settings_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "settings", "--section", "auth_settings"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["section"] == "auth_settings"
        assert data[0]["settings"]["idle_timeout"] == 60

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_section_not_found(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = mock_client({"system_settings": {"auth_settings": {}}})
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "settings", "--section", "nonexistent"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


# -------------------------------------------------------------------
# soar stats
# -------------------------------------------------------------------


class TestSoarStats:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_default_widgets(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Default stats fetches four widgets."""
        mock_resolve.return_value = soar_cfg()

        def side_effect(path: str, **kw: Any) -> Any:
            widget_responses: dict[str, Any] = {
                "widget_data/container_stats": {"total": 42},
                "widget_data/containers_workload": {"open": 10},
                "widget_data/sla_stats": {"overdue": 2},
                "widget_data/pending_approvals": {"count": 0},
            }
            return widget_responses.get(path, {})

        client = MagicMock()
        client.get.side_effect = side_effect
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4
        names = [r["widget"] for r in data]
        assert "container_stats" in names

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_specific_widget(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = mock_client(
            {"widget_data/roi_summary": {"roi_value": 1000, "actions": 50}}
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "stats", "--widget", "roi_summary"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["widget"] == "roi_summary"
        assert data[0]["data"]["roi_value"] == 1000

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_stats_unknown_widget_http_error_envelope(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Unknown widget passes the server's HTTP 400 through as-is.

        The live SOAR API answers a bogus widget name with HTTP 400
        ("Bad request. Provide a valid widget name"); the CLI keeps
        transparent pass-through — no remapping to not_found.
        """
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Bad request. Provide a valid widget name",
            kind="http",
            http_status=400,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "stats", "--widget", "bogus_widget"]
        )
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "http"
        assert payload["error"]["http_status"] == 400

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_widgets(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        # --list just emits the known widget names, no API call needed
        client = mock_client()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "stats", "--list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 17
        assert all("name" in r for r in data)


# -------------------------------------------------------------------
# soar meta
# -------------------------------------------------------------------


class TestSoarMeta:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_severities(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        severity_data: dict[str, Any] = {
            "count": 4,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "high", "color": "red"},
                {"id": 2, "name": "medium", "color": "orange"},
                {"id": 3, "name": "low", "color": "yellow"},
                {"id": 4, "name": "informational", "color": "green"},
            ],
        }
        client = mock_client({"severity": severity_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "severities"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4
        assert data[0]["name"] == "high"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_statuses(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        status_data: dict[str, Any] = {
            "count": 3,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "new", "is_default": True},
                {"id": 2, "name": "open", "is_default": False},
                {"id": 3, "name": "closed", "is_default": False},
            ],
        }
        client = mock_client({"container_status": status_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "statuses"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        names = [r["name"] for r in data]
        assert "new" in names
        assert "closed" in names

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_labels(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        options_data: dict[str, Any] = {
            "label": ["events", "notable", "custom_label"],
        }
        client = mock_client({"container_options": options_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "labels"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["label"] == "events"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_tags(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        options_data: dict[str, Any] = {
            "tags": ["malware", "phishing", "network"],
        }
        client = mock_client({"container_options": options_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "tags"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["tag"] == "malware"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cef(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        cef_data: dict[str, Any] = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"name": "sourceAddress", "data_type": "ip"},
                {"name": "destinationAddress", "data_type": "ip"},
            ],
        }
        client = mock_client({"cef": cef_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "cef"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "sourceAddress"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_features(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        feature_data: dict[str, Any] = {
            "count": 3,
            "num_pages": 1,
            "data": [
                {"name": "webhooks", "enabled": False},
                {"name": "indicators", "enabled": False},
                {"name": "approval_framework", "enabled": True},
            ],
        }
        client = mock_client({"feature_flag": feature_data})
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "features"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["name"] == "webhooks"
        assert data[0]["enabled"] is False

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_invalid_vocabulary(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Invalid vocab name prints usage and exits non-zero."""
        mock_resolve.return_value = soar_cfg()
        client = mock_client()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "meta", "bogus"])
        assert result.exit_code != 0
