"""Tests for soar ingest — validation, dry-run preview, empty results, automation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.commands.soar.ingest import _create_artifacts
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


PATCH_DEDUP_ART = "splunkctl.commands.soar.ingest.dedup_check_artifact"


class TestRunAutomationGating:
    """run_automation must land on the last *created* artifact, not last row."""

    @patch(PATCH_DEDUP_ART)
    def test_last_row_deduped_earlier_rows_created(self, mock_dedup: MagicMock) -> None:
        """When the last input row is deduped, the last created artifact
        must carry run_automation=True."""
        rows: list[dict[str, Any]] = [
            {"src": "10.0.0.1", "event_id": "e1", "_time": "t1"},
            {"src": "10.0.0.2", "event_id": "e2", "_time": "t2"},
            {"src": "10.0.0.3", "event_id": "e3", "_time": "t3"},
        ]
        # Last row (e3) already exists; first two are new.
        mock_dedup.side_effect = [None, None, 999]
        soar = MagicMock()
        soar.post.return_value = {"id": 100}

        created, skipped = _create_artifacts(
            soar,
            rows,
            container_id=1,
            sdi_field="event_id",
            severity_override=None,
            cim_map={},
            contains_map={},
            include_unmapped=False,
            no_automation=False,
        )

        assert created == 2
        assert skipped == 1

        # Exactly two artifact POST calls.
        art_calls = [c for c in soar.post.call_args_list if c[0][0] == "artifact"]
        assert len(art_calls) == 2

        # First artifact: run_automation=False
        assert art_calls[0].kwargs["body"]["run_automation"] is False
        # Second (last created): run_automation=True
        assert art_calls[1].kwargs["body"]["run_automation"] is True

    @patch(PATCH_DEDUP_ART)
    def test_no_automation_flag_suppresses_all(self, mock_dedup: MagicMock) -> None:
        """--no-automation suppresses run_automation on every artifact."""
        rows: list[dict[str, Any]] = [
            {"src": "10.0.0.1", "event_id": "e1", "_time": "t1"},
            {"src": "10.0.0.2", "event_id": "e2", "_time": "t2"},
        ]
        mock_dedup.return_value = None
        soar = MagicMock()
        soar.post.return_value = {"id": 100}

        created, skipped = _create_artifacts(
            soar,
            rows,
            container_id=1,
            sdi_field="event_id",
            severity_override=None,
            cim_map={},
            contains_map={},
            include_unmapped=False,
            no_automation=True,
        )

        assert created == 2
        assert skipped == 0
        art_calls = [c for c in soar.post.call_args_list if c[0][0] == "artifact"]
        for c in art_calls:
            assert c.kwargs["body"]["run_automation"] is False

    @patch(PATCH_DEDUP_ART)
    def test_all_rows_deduped_no_automation_set(self, mock_dedup: MagicMock) -> None:
        """When every row is deduped, no artifact is created and no
        run_automation flag is set anywhere."""
        rows: list[dict[str, Any]] = [
            {"src": "10.0.0.1", "event_id": "e1", "_time": "t1"},
            {"src": "10.0.0.2", "event_id": "e2", "_time": "t2"},
        ]
        mock_dedup.side_effect = [100, 200]
        soar = MagicMock()

        created, skipped = _create_artifacts(
            soar,
            rows,
            container_id=1,
            sdi_field="event_id",
            severity_override=None,
            cim_map={},
            contains_map={},
            include_unmapped=False,
            no_automation=False,
        )

        assert created == 0
        assert skipped == 2
        soar.post.assert_not_called()

    @patch(PATCH_DEDUP_ART)
    def test_single_artifact_gets_automation(self, mock_dedup: MagicMock) -> None:
        """A single non-deduped row gets run_automation=True."""
        rows: list[dict[str, Any]] = [
            {"src": "10.0.0.1", "event_id": "e1", "_time": "t1"},
        ]
        mock_dedup.return_value = None
        soar = MagicMock()
        soar.post.return_value = {"id": 100}

        created, _ = _create_artifacts(
            soar,
            rows,
            container_id=1,
            sdi_field="event_id",
            severity_override=None,
            cim_map={},
            contains_map={},
            include_unmapped=False,
            no_automation=False,
        )

        assert created == 1
        art_calls = [c for c in soar.post.call_args_list if c[0][0] == "artifact"]
        assert art_calls[0].kwargs["body"]["run_automation"] is True
