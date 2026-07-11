"""Tests for soar assets — list, get, create, update, delete, test."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _asset(
    asset_id: int = 1,
    name: str = "google_dns",
    app_id: int = 5,
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "name": name,
        "app": app_id,
        "configuration": {"dns_server": "8.8.8.8"},
        "description": "Google DNS",
    }


def _app_schema() -> dict[str, Any]:
    return {
        "id": 5,
        "name": "DNS",
        "configuration": {
            "dns_server": {
                "data_type": "string",
                "required": True,
                "default": "8.8.8.8",
            },
            "api_key": {
                "data_type": "password",
                "required": False,
            },
        },
    }


# ---- list ----


class TestAssetsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_all(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_asset()],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "assets", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "google_dns"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("fail", kind="error")
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "assets", "list"])
        assert result.exit_code == 1


# ---- get ----


class TestAssetsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_basic(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _asset()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "assets", "get", "1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "google_dns"


# ---- create ----


class TestAssetsCreate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run(
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
                "assets",
                "create",
                "--name",
                "test_asset",
                "--app-id",
                "5",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_set(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--set key=value populates configuration."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 10}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "assets",
                "create",
                "--name",
                "test_asset",
                "--app-id",
                "5",
                "--set",
                "dns_server=8.8.8.8",
            ],
        )
        assert result.exit_code == 0
        _, kwargs = client.post.call_args
        body = kwargs.get("body", {})
        assert body["configuration"]["dns_server"] == "8.8.8.8"


# ---- update ----


class TestAssetsUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_fetch_merge_post(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Update merges new config into existing asset config."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _asset()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "assets",
                "update",
                "1",
                "--set",
                "new_key=val",
            ],
        )
        assert result.exit_code == 0
        _, kwargs = client.post.call_args
        body = kwargs.get("body", {})
        # Must preserve existing dns_server AND add new_key
        assert body["configuration"]["dns_server"] == "8.8.8.8"
        assert body["configuration"]["new_key"] == "val"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_replace_mode(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--replace sends only the new config without merge."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _asset()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "assets",
                "update",
                "1",
                "--replace",
                "--set",
                "only_this=yes",
            ],
        )
        assert result.exit_code == 0
        _, kwargs = client.post.call_args
        body = kwargs.get("body", {})
        assert body["configuration"] == {"only_this": "yes"}
        # Must NOT contain old dns_server
        assert "dns_server" not in body["configuration"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _asset()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "assets", "update", "1", "--set", "k=v"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_secrets_masked(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Password-type config keys must be masked in dry-run preview."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        # Return app schema with password-type field
        client.get.side_effect = [
            {
                "id": 1,
                "name": "test",
                "app": 5,
                "configuration": {"api_key": "secret123"},
            },
            _app_schema(),
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "assets",
                "update",
                "1",
                "--set",
                "api_key=newsecret",
            ],
        )
        assert result.exit_code == 0
        # The dry-run stderr should mask the password value
        assert "newsecret" not in result.stderr
        assert "****" in result.stderr


# ---- delete ----


class TestAssetsDelete:
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

        result = CliRunner().invoke(cli, ["--json", "soar", "assets", "delete", "1"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_applies(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.return_value = {"id": 1}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "assets", "delete", "1"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once()


# ---- test (connectivity) ----


class TestAssetsTest:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_test_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()

        result = CliRunner().invoke(cli, ["--json", "soar", "assets", "test", "1"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_test_triggers_and_polls(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """test posts to asset/<id>/test then polls app_status."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {
                    "app_id": 5,
                    "asset_id": 1,
                    "status": "success",
                    "message": "Connectivity test passed",
                }
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "assets", "test", "1"]
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        post_args = client.post.call_args
        assert "asset/1/test" in post_args[0] or post_args[0][0] == "asset/1/test"


# ---- ingest-status ----


class TestIngestStatus:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_ingest_status(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {
                "count": 1,
                "num_pages": 1,
                "data": [
                    {
                        "asset_id": 1,
                        "asset_name": "google_dns",
                        "app_id": 5,
                        "status": "success",
                        "message": "ok",
                    }
                ],
            },
            {
                "count": 1,
                "num_pages": 1,
                "data": [
                    {
                        "app_id": 5,
                        "asset_id": 1,
                        "status": "success",
                    }
                ],
            },
        ]
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "ingest-status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_ingest_status_error(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("fail", kind="error")
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "ingest-status"])
        assert result.exit_code == 1
