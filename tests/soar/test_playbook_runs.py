"""Tests for soar playbooks run — launch, name resolution, polling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
PATCH_MONOTONIC = "splunkctl.commands.soar.playbook_runs.time.monotonic"
PATCH_SLEEP = "splunkctl.commands.soar.playbook_runs.time.sleep"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


class TestPlaybooksRun:
    """POST /rest/playbook_run — guarded mutation."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "playbooks", "run", "my_playbook", "--container", "42"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        assert "<name: my_playbook>" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_by_name_resolves_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Non-numeric playbook arg resolves name -> id."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 7, "name": "my_playbook"}],
        }
        client.post.return_value = {"success": True, "id": 101}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "my_playbook",
                "--container",
                "42",
            ],
        )
        assert result.exit_code == 0
        client.get.assert_called_once()
        get_params = client.get.call_args[1]["params"]
        assert get_params["_filter_name"] == '"my_playbook"'
        client.post.assert_called_once()
        body = client.post.call_args[1]["body"]
        assert body["playbook_id"] == 7
        assert body["container_id"] == 42
        assert body["run"] is True

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_by_numeric_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Numeric playbook arg is used directly as playbook_id."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 102}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
            ],
        )
        assert result.exit_code == 0
        client.get.assert_not_called()
        body = client.post.call_args[1]["body"]
        assert body["playbook_id"] == 7

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_scope_and_inputs(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """--scope and --input are forwarded in the POST body."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 103}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
                "--scope",
                "new",
                "--input",
                "ip=1.2.3.4",
                "--input",
                "domain=evil.com",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["scope"] == "new"
        assert body["inputs"] == {"ip": "1.2.3.4", "domain": "evil.com"}

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_name_not_found(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Unknown playbook name -> not_found error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "nonexistent",
                "--container",
                "42",
            ],
        )
        assert result.exit_code == 1
        assert "not_found" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_run_server_404(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Server validates playbook_id; 404 surfaces as not_found."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            'Playbook "999" not found',
            kind="not_found",
            http_status=404,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "999",
                "--container",
                "42",
            ],
        )
        assert result.exit_code == 1
        assert "not_found" in result.stderr


class TestPlaybooksRunWait:
    """--wait polling tests with mocked time."""

    @patch(PATCH_SLEEP)
    @patch(PATCH_MONOTONIC)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_wait_polls_to_success(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Polls GET /rest/playbook_run/<id> until terminal status."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        mock_monotonic.side_effect = [0.0, 1.0, 2.0]
        client = MagicMock()
        client.post.return_value = {"received": True, "id": 201}
        client.get.side_effect = [
            {"status": "running", "id": 201},
            {"status": "success", "id": 201, "message": '{"msg": "ok"}'},
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
                "--wait",
            ],
        )
        assert result.exit_code == 0
        assert client.get.call_count == 2
        client.get.assert_any_call("playbook_run/201", params={})
        mock_sleep.assert_called()

    @patch(PATCH_SLEEP)
    @patch(PATCH_MONOTONIC)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_wait_timeout(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """--timeout N exits with timeout error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        mock_monotonic.side_effect = [0.0, 1.0, 100.0]
        client = MagicMock()
        client.post.return_value = {"received": True, "id": 202}
        client.get.side_effect = [
            {"status": "running", "id": 202},
            {"status": "running", "id": 202},
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
                "--wait",
                "--timeout",
                "30",
            ],
        )
        assert result.exit_code == 1
        assert "timeout" in result.stderr.lower()

    @patch(PATCH_SLEEP)
    @patch(PATCH_MONOTONIC)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_wait_message_pretty_printed(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Terminal message that parses as JSON is pretty-printed."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        mock_monotonic.side_effect = [0.0, 1.0]
        client = MagicMock()
        client.post.return_value = {"received": True, "id": 203}
        client.get.return_value = {
            "status": "success",
            "id": 203,
            "message": '{"result": "done", "actions": 0}',
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
                "--wait",
            ],
        )
        assert result.exit_code == 0
        combined = result.output + result.stderr
        assert "result" in combined

    @patch(PATCH_SLEEP)
    @patch(PATCH_MONOTONIC)
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_wait_failed_status_exits_1(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
        mock_monotonic: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Terminal 'failed' status exits 1."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        mock_monotonic.side_effect = [0.0, 1.0]
        client = MagicMock()
        client.post.return_value = {"received": True, "id": 204}
        client.get.return_value = {
            "status": "failed",
            "id": 204,
            "message": "playbook error",
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "run",
                "7",
                "--container",
                "42",
                "--wait",
            ],
        )
        assert result.exit_code == 1


class TestRunNameSuffixRetry:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_bare_module_name_suffix_resolves(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """'investigate' finds 'local/investigate' like sibling commands do."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": []},  # exact-name miss
            {"data": [{"id": 7, "name": "local/investigate"}]},  # suffix hit
        ]
        client.post.return_value = {"success": True, "id": 101}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "run",
                "investigate",
                "--container",
                "42",
            ],
        )
        assert result.exit_code == 0
        suffix_params = client.get.call_args_list[1][1]["params"]
        assert suffix_params["_filter_name__endswith"] == '"/investigate"'
        assert client.post.call_args[1]["body"]["playbook_id"] == 7
