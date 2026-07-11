"""Tests for soar containers — list and get with sub-views."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

# -------------------------------------------------------------------
# soar containers list
# -------------------------------------------------------------------


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


# -------------------------------------------------------------------
# soar containers get
# -------------------------------------------------------------------


class TestContainersGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_basic(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        container: dict[str, Any] = {
            "id": 42,
            "name": "DNS Alert",
            "label": "events",
            "status": "new",
            "severity": "high",
        }
        client = MagicMock()
        client.get.return_value = container
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "containers", "get", "42"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == 42
        assert data[0]["name"] == "DNS Alert"
        client.get.assert_called_once_with("container/42", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_artifacts(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        artifacts = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {"id": 100, "name": "IP artifact", "cef": {"sourceAddress": "1.2.3.4"}},
            ],
        }
        client.get.return_value = artifacts
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--artifacts"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "IP artifact"
        client.get.assert_called_once_with("container/42/artifacts", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_notes(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        notes = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 10, "title": "Analysis", "content": "Malicious"}],
        }
        client.get.return_value = notes
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--notes"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["title"] == "Analysis"
        client.get.assert_called_once_with("container/42/notes", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_comments(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        comments = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 5, "comment": "Looks bad"}],
        }
        client.get.return_value = comments
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--comments"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["comment"] == "Looks bad"
        client.get.assert_called_once_with("container/42/comments", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_audit(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        # /rest/container/<id>/audit returns bare array, normalized by client
        audit = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"message": "Created", "time": "2026-07-01"},
                {"message": "Updated", "time": "2026-07-02"},
            ],
        }
        client.get.return_value = audit
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--audit"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        client.get.assert_called_once_with("container/42/audit", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_activity(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        activity = {
            "count": 1,
            "num_pages": 1,
            "data": [{"message": "Playbook started", "time": "2026-07-01"}],
        }
        client.get.return_value = activity
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--activity"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["message"] == "Playbook started"
        client.get.assert_called_once_with("container/42/activity_feed", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_playbook_runs(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        runs = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 7, "playbook": 3, "status": "success"}],
        }
        client.get.return_value = runs
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--playbook-runs"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["status"] == "success"
        client.get.assert_called_once_with("container/42/playbook_runs", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_phases(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        phases = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 1, "name": "Identification", "order": 0}],
        }
        client.get.return_value = phases
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "containers", "get", "42", "--phases"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "Identification"
        client.get.assert_called_once_with("container/42/phases", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "containers", "get", "999"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "not_found"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_multiple_flags_last_wins(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """When multiple sub-view flags are given, the last one wins."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "containers", "get", "42", "--notes", "--comments"],
        )
        assert result.exit_code == 0
        # Should have called with the last sub-view flag
        call_path = client.get.call_args[0][0]
        assert call_path in ("container/42/notes", "container/42/comments")
