"""Tests for soar indicators — feature flag detection, list, get, pivot, stats."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

# -- Helpers ------------------------------------------------------------------

_FLAG_ON: dict[str, Any] = {
    "count": 1,
    "num_pages": 1,
    "data": [{"name": "use_indicators", "value": True}],
}
_FLAG_OFF: dict[str, Any] = {
    "count": 1,
    "num_pages": 1,
    "data": [{"name": "use_indicators", "value": False}],
}
_FLAG_MISSING: dict[str, Any] = {"count": 0, "num_pages": 1, "data": []}


def _client_with_flag(
    flag_response: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock client that returns *flag_response* for feature_flag."""
    client = MagicMock()
    responses: dict[str, Any] = {"feature_flag": flag_response}
    if extra:
        responses.update(extra)

    def get_side(path: str, **kw: Any) -> Any:
        for key, val in responses.items():
            if path == key or path.startswith(key):
                return val
        return {}

    client.get.side_effect = get_side
    return client


# -- Indicator flag-off tests -------------------------------------------------


class TestIndicatorFlagOff:
    """All indicator commands exit 1 with actionable message when flag is off."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_flag_off(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(_FLAG_OFF)

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 1
        assert "Indicators feature is disabled" in result.stderr

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_flag_off(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(_FLAG_OFF)

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "get", "8.8.8.8"]
        )
        assert result.exit_code == 1
        assert "use_indicators" in result.stderr

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_pivot_flag_off(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(_FLAG_OFF)

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "pivot", "evil.com"]
        )
        assert result.exit_code == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_stats_flag_off(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(_FLAG_OFF)

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "stats"])
        assert result.exit_code == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_flag_missing_treated_as_off(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(_FLAG_MISSING)

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 1
        assert "Feature Toggles" in result.stderr

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_flag_endpoint_unreachable(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        client = MagicMock()
        client.get.side_effect = SOARError("boom", kind="http", http_status=500)
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 1


# -- Indicator flag-on tests --------------------------------------------------


class TestIndicatorList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        indicators = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "value": "8.8.8.8", "type": "ip"},
                {"id": 2, "value": "evil.com", "type": "domain"},
            ],
        }
        mock_cls.return_value = _client_with_flag(_FLAG_ON, {"indicator": indicators})

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["value"] == "8.8.8.8"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_type_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON, {"indicator": {"count": 0, "num_pages": 1, "data": []}}
        )

        CliRunner().invoke(
            cli,
            ["--json", "soar", "indicators", "list", "--type", "ip"],
        )
        client = mock_cls.return_value
        calls = [c for c in client.get.call_args_list if c[0][0] == "indicator"]
        assert len(calls) == 1
        params = calls[0][1].get("params", {})
        assert params.get("_filter_type") == '"ip"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_limit(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON, {"indicator": {"count": 0, "num_pages": 1, "data": []}}
        )

        CliRunner().invoke(
            cli,
            ["--json", "soar", "indicators", "list", "--limit", "10"],
        )
        client = mock_cls.return_value
        calls = [c for c in client.get.call_args_list if c[0][0] == "indicator"]
        params = calls[0][1].get("params", {})
        assert params["page_size"] == 10

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON, {"indicator": {"count": 0, "num_pages": 1, "data": []}}
        )

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "feature_flag":
                return _FLAG_ON
            raise SOARError("server error", kind="http", http_status=500)

        client.get.side_effect = get_side
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "list"])
        assert result.exit_code == 1


class TestIndicatorGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_value(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        indicator_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 42, "value": "8.8.8.8", "type": "ip"}],
        }
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON, {"indicator_by_value": indicator_resp}
        )

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "get", "8.8.8.8"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["value"] == "8.8.8.8"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "feature_flag":
                return _FLAG_ON
            if path == "indicator_by_value":
                raise SOARError("not found", kind="not_found", http_status=404)
            return {}

        client.get.side_effect = get_side
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "get", "unknown"]
        )
        assert result.exit_code == 1


class TestIndicatorPivot:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_pivot_renders_containers(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        pivot_resp: dict[str, Any] = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 10, "name": "DNS Alert", "label": "events"},
                {"id": 20, "name": "Phishing", "label": "events"},
            ],
        }
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON, {"indicator_common_container": pivot_resp}
        )

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "pivot", "evil.com"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "DNS Alert"
        assert data[1]["name"] == "Phishing"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_pivot_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = _client_with_flag(
            _FLAG_ON,
            {"indicator_common_container": {"count": 0, "num_pages": 1, "data": []}},
        )

        result = CliRunner().invoke(
            cli, ["--json", "soar", "indicators", "pivot", "clean.com"]
        )
        assert result.exit_code == 0
        assert json.loads(result.output) == []


class TestIndicatorStats:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_stats_merges_type_and_severity(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        type_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [{"type": "ip", "count": 50}],
        }
        sev_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [{"severity": "high", "count": 10}],
        }
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "feature_flag":
                return _FLAG_ON
            if path == "indicator_stats_type":
                return type_resp
            if path == "indicator_stats_severity":
                return sev_resp
            return {}

        client.get.side_effect = get_side
        mock_cls.return_value = client
        mock_resolve.return_value = soar_cfg()

        result = CliRunner().invoke(cli, ["--json", "soar", "indicators", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        sources = [r["source"] for r in data]
        assert "indicator_stats_type" in sources
        assert "indicator_stats_severity" in sources
