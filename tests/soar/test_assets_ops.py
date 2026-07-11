"""Tests for soar assets — test connectivity, ingest-status."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


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
