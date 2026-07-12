"""Tests for container owner/role resolution and read-back verification."""

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


class TestOwnerResolution:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_numeric_username_resolves_by_name_first(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """An all-digit username (AD employee id) must not be sent as owner_id."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": [{"id": 7, "username": "10234"}]},  # name lookup hits
            {"id": 5, "owner": 7},  # read-back verify
        ]
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "5", "--owner", "10234"],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body == {"owner_id": 7}  # the user's id, not int("10234")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_numeric_value_falls_back_to_raw_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": []},  # no user named "42"
            {"id": 5, "owner": 42},  # read-back verify
        ]
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "5", "--owner", "42"],
        )
        assert result.exit_code == 0
        assert client.post.call_args[1]["body"] == {"owner_id": 42}

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_unicode_digit_owner_is_clean_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """'²'.isdigit() is True but int() rejects it — no traceback."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "5", "--owner", "²"],
        )
        assert result.exit_code == 1
        assert "not found" in result.stderr
        client.post.assert_not_called()


class TestReadBackVerification:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_bulk_verifies_every_container(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """A silent-ignore on the 2nd container must fail the command."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": [{"id": 3, "username": "alice"}]},  # user lookup
            {"id": 1, "owner": 3},  # container 1: stuck
            {"id": 2, "owner": 9, "owner_name": "bob"},  # container 2: ignored
        ]
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "1", "2", "--owner", "alice"],
        )
        assert result.exit_code == 1
        assert "container 2" in result.stderr
        assert "did not stick" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_unverifiable_readback_warns_not_silent(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """A failed verification GET is reported, never treated as verified-OK."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": [{"id": 3, "username": "alice"}]},  # user lookup
            SOARError("forbidden", kind="permission", http_status=403),
        ]
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "1", "--owner", "alice"],
        )
        assert result.exit_code == 0  # the write itself succeeded
        assert "Could not verify" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_string_id_in_readback_still_verifies(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """A server returning owner as a numeric string is not a mismatch."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {"data": [{"id": 3, "username": "alice"}]},
            {"id": 1, "owner": "3"},  # string-typed id
        ]
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "containers", "assign", "1", "--owner", "alice"],
        )
        assert result.exit_code == 0
        assert "did not stick" not in result.stderr
