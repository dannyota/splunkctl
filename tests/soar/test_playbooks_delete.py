"""Tests for soar playbooks delete — guard order, strict names, reporting."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


class TestPlaybooksDelete:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run_does_no_network_io(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Preview must not resolve names — no client calls before guard."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["soar", "playbooks", "delete", "42", "local/old_pb"]
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        # The user-typed identifiers appear verbatim in the preview.
        assert "42" in result.stderr
        assert "local/old_pb" in result.stderr
        assert "resolved to id at apply time" in result.stderr
        client.get.assert_not_called()
        client.web_delete_playbooks.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.web_delete_playbooks.return_value = {
            "done_count": 2,
            "fail_count": 0,
            "changes": ["deleted 8", "deleted 9"],
            "errors": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "soar", "playbooks", "delete", "8", "9"]
        )
        assert result.exit_code == 0
        client.web_delete_playbooks.assert_called_once_with([8, 9])
        assert "Deleted 2 playbook(s)." in result.stderr
        client.get.assert_not_called()  # ids need no resolution

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_exact_name_resolves(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"data": [{"id": 7, "name": "local/pb"}]}
        client.web_delete_playbooks.return_value = {
            "done_count": 1,
            "fail_count": 0,
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "soar", "playbooks", "delete", "local/pb"]
        )
        assert result.exit_code == 0
        assert "Resolved 'local/pb' to playbook id 7" in result.stderr
        client.web_delete_playbooks.assert_called_once_with([7])

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_suffix_match_refused_with_hint(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Deletion never guesses: a suffix-only hit is a did-you-mean error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": []},  # exact-name miss
            {"data": [{"id": 42, "name": "community/pb"}]},  # suffix hit
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "delete", "pb"])
        assert result.exit_code == 1
        assert "Did you mean 'community/pb' (id 42)?" in result.stderr
        client.web_delete_playbooks.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_fail_count_exits_nonzero(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.web_delete_playbooks.return_value = {
            "done_count": 0,
            "fail_count": 1,
            "changes": [],
            "errors": ["playbook 8 is read-only"],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "delete", "8"])
        assert result.exit_code == 1
        assert "playbook 8 is read-only" in result.stderr
        assert "1 playbook(s) failed to delete." in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_zero_done_warns(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.web_delete_playbooks.return_value = {"done_count": 0, "fail_count": 0}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "soar", "playbooks", "delete", "999"]
        )
        assert result.exit_code == 0
        assert "No playbooks deleted" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_client_error_reported(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.web_delete_playbooks.side_effect = SOARError(
            "SOAR Web login failed: invalid credentials.", kind="auth"
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "delete", "8"])
        assert result.exit_code == 1
        assert "invalid credentials" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_unicode_digit_treated_as_name(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """'²'.isdigit() is True but int() rejects it — must not traceback."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "delete", "²"])
        assert result.exit_code == 1
        assert "not found" in result.stderr
        client.web_delete_playbooks.assert_not_called()
