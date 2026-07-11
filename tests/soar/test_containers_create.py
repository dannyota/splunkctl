"""Tests for soar containers create — SDI dedup, tags, fields, dry-run."""

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


class TestContainerCreate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Create without --yes prints dry-run preview."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "containers", "create", "--name", "test", "--label", "events"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        assert "SOAR @ soar.test:8443" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Create with --yes calls POST /rest/container."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 99}
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "create",
                "--name",
                "test",
                "--label",
                "events",
                "--severity",
                "high",
                "--sdi",
                "SDI001",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        post_args = client.post.call_args
        assert post_args[0][0] == "container"
        body = post_args[1]["body"]
        assert body["name"] == "test"
        assert body["label"] == "events"
        assert body["severity"] == "high"
        assert body["source_data_identifier"] == "SDI001"
        assert body["run_automation"] is False

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_sdi_dedup_precheck(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Create with --sdi queries first; existing SDI exits 1."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 42, "name": "existing"}],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "create",
                "--name",
                "test",
                "--label",
                "events",
                "--sdi",
                "SDI001",
            ],
        )
        assert result.exit_code == 1
        assert "SDI001" in result.stderr
        assert "42" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_server_sdi_duplicate(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Server-side SDI duplicate surfaces existing_container_id."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        client.post.side_effect = SOARError(
            "duplicate SDI",
            kind="http",
            http_status=400,
            data={"failed": True, "existing_container_id": 77},
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "create",
                "--name",
                "test",
                "--label",
                "events",
                "--sdi",
                "SDI001",
            ],
        )
        assert result.exit_code == 1
        assert "existing_container_id=77" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_tags_and_fields(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Create with --tag and --field passes them in the body."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 100}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "create",
                "--name",
                "test",
                "--label",
                "events",
                "--tag",
                "malware",
                "--tag",
                "phishing",
                "--field",
                "priority=P1",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["tags"] == ["malware", "phishing"]
        assert body["custom_fields"] == {"priority": "P1"}
