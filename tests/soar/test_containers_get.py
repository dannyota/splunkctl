"""Tests for soar containers get — sub-view flags and error paths."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


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
        # The LAST flag on the command line must win.
        call_path = client.get.call_args[0][0]
        assert call_path == "container/42/comments"
