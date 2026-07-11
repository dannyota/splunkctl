"""Tests for soar containers list — filters, pagination, validation."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


class TestContainersList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Bare list returns container rows."""
        mock_resolve.return_value = soar_cfg()
        containers: dict[str, Any] = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "DNS Alert", "label": "events", "status": "new"},
                {"id": 2, "name": "Phishing", "label": "events", "status": "open"},
            ],
        }
        client = MagicMock()
        client.get.return_value = containers
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "containers", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "DNS Alert"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_label_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--label passes _filter_label to the API."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--label", "events"]
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_label") == '"events"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_status_resolves_name(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--status resolves numeric id via container_status lookup."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "container_status":
                return {
                    "count": 3,
                    "num_pages": 1,
                    "data": [
                        {"id": 1, "name": "new"},
                        {"id": 2, "name": "open"},
                        {"id": 3, "name": "closed"},
                    ],
                }
            return {"count": 0, "num_pages": 1, "data": []}

        client.get.side_effect = get_side
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--status", "open"]
        )
        # The second get call should be container with _filter_status
        calls = client.get.call_args_list
        container_call = [c for c in calls if c[0][0] == "container"]
        assert len(container_call) == 1
        params = container_call[0][1].get("params", {})
        assert params.get("_filter_status") == '"open"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_severity(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--severity", "high"]
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_severity") == '"high"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_owner(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--owner", "admin"]
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_owner_name") == '"admin"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_since(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--since maps to _filter_create_time__gt."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            ["--json", "soar", "containers", "list", "--since", "2026-07-01"],
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_create_time__gt") == '"2026-07-01"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_type_event(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--type", "event"]
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_container_type") == '"default"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_type_case(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--type", "case"]
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_container_type") == '"case"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_raw_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--filter passes raw Django filter key=value."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "containers",
                "list",
                "--filter",
                '_filter_name__icontains="dns"',
            ],
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_name__icontains") == '"dns"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_limit_offset(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--offset with --limit computes page = offset // limit."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "containers",
                "list",
                "--limit",
                "5",
                "--offset",
                "10",
            ],
        )
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params["page_size"] == 5
        assert params["page"] == 2  # offset 10 / page_size 5 = page 2

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_offset_without_limit_errors(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--offset without --limit exits 1 with a usage error."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--offset", "20"]
        )
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"
        assert "--offset requires --limit" in payload["error"]["message"]
        client.get.assert_not_called()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_offset_not_multiple_of_limit_errors(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--offset must be a multiple of --limit."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "containers",
                "list",
                "--limit",
                "5",
                "--offset",
                "7",
            ],
        )
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"
        assert "multiple" in payload["error"]["message"]
        client.get.assert_not_called()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_empty(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "containers", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_status_invalid(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Unknown status name produces an error."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "container_status":
                return {
                    "count": 2,
                    "num_pages": 1,
                    "data": [
                        {"id": 1, "name": "new"},
                        {"id": 2, "name": "open"},
                    ],
                }
            return {"count": 0, "num_pages": 1, "data": []}

        client.get.side_effect = get_side
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--status", "bogus"]
        )
        assert result.exit_code == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_status_lookup_failure_warns(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """A failed container_status lookup warns and passes through."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "container_status":
                raise SOARError("boom", kind="http", http_status=500)
            return {"count": 0, "num_pages": 1, "data": []}

        client.get.side_effect = get_side
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "list", "--status", "open"]
        )
        assert result.exit_code == 0
        assert "could not validate status name" in result.stderr
        # The container query still went out with the status filter.
        calls = client.get.call_args_list
        container_call = [c for c in calls if c[0][0] == "container"]
        assert len(container_call) == 1
        params = container_call[0][1].get("params", {})
        assert params.get("_filter_status") == '"open"'
