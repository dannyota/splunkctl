"""Tests for soar ingest — validation, dry-run preview, empty results."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
PATCH_SOAR_CLIENT = "splunkctl.commands.soar.ingest.get_soar_client"
PATCH_FETCH = "splunkctl.commands.soar.ingest.fetch_spl_results"

SYNTH_ROWS: list[dict[str, Any]] = [
    {
        "src": "10.0.0.1",
        "dest": "10.0.0.2",
        "dest_port": "443",
        "user": "admin",
        "_time": "2026-01-01T00:00:00",
        "source": "test",
    },
]


class TestIngestValidation:
    """Argument validation (no SIEM/SOAR calls)."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_no_spl_no_sid(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(cli, ["--json", "soar", "ingest"])
        assert result.exit_code == 1

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_both_spl_and_sid(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        result = CliRunner().invoke(
            cli, ["--json", "soar", "ingest", "--spl", "x", "--sid", "y"]
        )
        assert result.exit_code == 1


class TestIngestDryRun:
    """Dry-run preview (default, no --yes)."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run_shows_preview(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = SYNTH_ROWS

        soar = MagicMock()
        mock_soar_client.return_value = soar

        result = CliRunner().invoke(
            cli, ["--json", "soar", "ingest", "--spl", "| makeresults"]
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        assert "Containers: 1" in result.stderr
        assert "artifact(s)" in result.stderr
        soar.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run_shows_mapping_table(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = SYNTH_ROWS

        result = CliRunner().invoke(
            cli, ["--json", "soar", "ingest", "--spl", "| makeresults"]
        )
        assert "CIM -> CEF mapping" in result.stderr

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run_shows_sample_cef(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = SYNTH_ROWS

        result = CliRunner().invoke(
            cli, ["--json", "soar", "ingest", "--spl", "| makeresults"]
        )
        assert "Sample CEF payload" in result.stderr
        assert "sourceAddress" in result.stderr


class TestIngestEmptyResults:
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_empty_results_exits_cleanly(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_fetch.return_value = []

        result = CliRunner().invoke(
            cli, ["--json", "soar", "ingest", "--spl", "| makeresults"]
        )
        assert result.exit_code == 0
        assert "Nothing to ingest" in result.stderr
