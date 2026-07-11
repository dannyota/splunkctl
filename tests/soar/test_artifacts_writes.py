"""Tests for soar artifacts — update and delete mutations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.commands.soar.artifacts.cfg_mod.resolve_soar"


class TestArtifactsUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run_default(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "artifacts",
                "update",
                "42",
                "--cef",
                "sourceAddress=9.9.9.9",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_fetch_merge_cef(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Update merges new CEF keys into existing cef dict."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 42,
            "name": "IP",
            "cef": {
                "sourceAddress": "1.2.3.4",
                "destinationPort": "80",
            },
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "update",
                "42",
                "--cef",
                "sourceAddress=9.9.9.9",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["cef"]["sourceAddress"] == "9.9.9.9"
        assert body["cef"]["destinationPort"] == "80"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_replace_cef(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--replace-cef sends only the new CEF, no merge."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 42,
            "name": "IP",
            "cef": {
                "sourceAddress": "1.2.3.4",
                "destinationPort": "80",
            },
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "update",
                "42",
                "--cef",
                "sourceAddress=9.9.9.9",
                "--replace-cef",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["cef"] == {"sourceAddress": "9.9.9.9"}
        assert "destinationPort" not in body["cef"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_name(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--name updates the artifact name."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 42,
            "name": "Old",
            "cef": {},
        }
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "update",
                "42",
                "--name",
                "New",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["name"] == "New"


class TestArtifactsDelete:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "artifacts", "delete", "42"]
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.delete.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.return_value = {"id": "42"}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "artifacts", "delete", "42"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("artifact/42")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "artifacts", "delete", "999"],
        )
        assert result.exit_code == 1
