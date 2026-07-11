"""Tests for soar ingest — apply path, dedup, grouping, automation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
PATCH_SOAR_CLIENT = "splunkctl.commands.soar.ingest.get_soar_client"
PATCH_FETCH = "splunkctl.commands.soar.ingest.fetch_spl_results"

_SYNTH_ROWS: list[dict[str, Any]] = [
    {
        "src": "10.0.0.1",
        "dest": "10.0.0.2",
        "dest_port": "443",
        "user": "admin",
        "_time": "2026-01-01T00:00:00",
        "source": "test",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _soar_get(path: str, **kw: Any) -> dict[str, Any]:
    """Default SOAR GET mock — empty results for dedup checks."""
    if path == "container_options":
        return {"label": [{"name": "events"}, {"name": "notable"}]}
    if path == "container":
        return {"count": 0, "num_pages": 1, "data": []}
    if path == "artifact":
        return {"count": 0, "num_pages": 1, "data": []}
    return {}


def _soar_get_dedup_container(path: str, **kw: Any) -> dict[str, Any]:
    """SOAR GET mock — container SDI already exists."""
    if path == "container_options":
        return {"label": [{"name": "events"}]}
    if path == "container":
        return {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 42, "source_data_identifier": "existing"}],
        }
    if path == "artifact":
        return {"count": 0, "num_pages": 1, "data": []}
    return {}


# ---------------------------------------------------------------------------
# Apply path
# ---------------------------------------------------------------------------


class TestIngestApply:
    """With --yes: container + artifact creation."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_creates_container_and_artifact(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},  # container
            {"success": True, "id": 200},  # artifact
        ]
        mock_soar_client.return_value = soar

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "| makeresults"],
        )
        assert result.exit_code == 0
        container_body = soar.post.call_args_list[0][1]["body"]
        assert container_body["label"] == "events"
        assert container_body["sensitivity"] == "amber"
        art_body = soar.post.call_args_list[1][1]["body"]
        assert art_body["container_id"] == 100
        assert soar.post.call_count == 2
        assert "containers_created" in result.output

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_cef_has_correct_fields(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "| makeresults"],
        )
        art_body = soar.post.call_args_list[1][1]["body"]
        assert art_body["cef"]["sourceAddress"] == "10.0.0.1"
        assert art_body["cef"]["destinationAddress"] == "10.0.0.2"
        assert art_body["cef"]["destinationPort"] == "443"
        assert "ip" in art_body["cef_types"]["sourceAddress"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_container_label_and_sensitivity(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "ingest",
                "--spl",
                "| makeresults",
                "--label",
                "notable",
                "--sensitivity",
                "green",
            ],
        )
        container_body = soar.post.call_args_list[0][1]["body"]
        assert container_body["label"] == "notable"
        assert container_body["sensitivity"] == "green"


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestIngestDedup:
    """SDI dedup — container and artifact level."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_container_sdi_dedup_skips(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """When container SDI already exists, skip creation."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get_dedup_container(path, **kw)
        mock_soar_client.return_value = soar

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "| makeresults"],
        )
        assert result.exit_code == 0
        assert "already exists" in result.stderr.lower()
        soar.post.assert_not_called()
        assert "containers_skipped" in result.output

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_server_side_sdi_dedup(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Server returns existing_container_id -> skip."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = SOARError(
            "Duplicate SDI",
            kind="conflict",
            http_status=400,
            data={"failed": True, "existing_container_id": 55},
        )
        mock_soar_client.return_value = soar

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "| makeresults"],
        )
        assert result.exit_code == 0
        assert "already exists" in result.stderr.lower()
        assert "containers_skipped" in result.output


# ---------------------------------------------------------------------------
# Grouping + automation batching
# ---------------------------------------------------------------------------


class TestIngestGrouping:
    """--grouping: all rows into one container."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_grouping_single_container(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        rows = [
            {"src": "10.0.0.1", "dest": "10.0.0.2", "_time": "t1", "source": "s"},
            {"src": "10.0.0.3", "dest": "10.0.0.4", "_time": "t2", "source": "s"},
        ]
        mock_fetch.return_value = rows

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
            {"success": True, "id": 201},
        ]
        mock_soar_client.return_value = soar

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "ingest",
                "--spl",
                "| makeresults",
                "--grouping",
            ],
        )
        assert result.exit_code == 0
        assert soar.post.call_count == 3
        assert "containers_created" in result.output


class TestIngestAutomation:
    """run_automation batching — last-artifact-true unless --no-automation."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_last_artifact_true(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        rows = [
            {"src": "10.0.0.1", "_time": "t1", "source": "s"},
            {"src": "10.0.0.2", "_time": "t2", "source": "s"},
        ]
        mock_fetch.return_value = rows

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
            {"success": True, "id": 201},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "ingest",
                "--spl",
                "| makeresults",
                "--grouping",
            ],
        )
        art1 = soar.post.call_args_list[1][1]["body"]
        assert art1["run_automation"] is False
        art2 = soar.post.call_args_list[2][1]["body"]
        assert art2["run_automation"] is True

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_no_automation_all_false(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = _SYNTH_ROWS

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "ingest",
                "--spl",
                "| makeresults",
                "--no-automation",
            ],
        )
        art = soar.post.call_args_list[1][1]["body"]
        assert art["run_automation"] is False
