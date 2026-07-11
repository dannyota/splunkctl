"""Tests for soar ingest — notable-specific handling, severity override."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
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

_NOTABLE_ROW: dict[str, Any] = {
    "event_id": "EVT-A1B2C3",
    "rule_name": "Brute Force Access Behavior Detected",
    "severity": "high",
    "urgency": "critical",
    "src": "192.168.1.100",
    "dest": "10.0.0.5",
    "user": "jsmith",
    "security_domain": "access",
    "risk_score": "85",
    "_time": "2026-07-11T12:00:00",
    "source": "notable",
}


def _soar_get(path: str, **kw: Any) -> dict[str, Any]:
    """Default SOAR GET mock — empty results for dedup checks."""
    if path == "container_options":
        return {"label": [{"name": "events"}, {"name": "notable"}]}
    if path == "container":
        return {"count": 0, "num_pages": 1, "data": []}
    if path == "artifact":
        return {"count": 0, "num_pages": 1, "data": []}
    return {}


class TestIngestNotable:
    """Notable-specific handling (canned fixture, no live ES)."""

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_notable_uses_event_id_sdi(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = [_NOTABLE_ROW]

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "index=notable"],
        )
        container_body = soar.post.call_args_list[0][1]["body"]
        assert container_body["source_data_identifier"] == "EVT-A1B2C3"
        assert "Brute Force" in container_body["name"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_notable_severity_mapping(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = [_NOTABLE_ROW]

        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: _soar_get(path, **kw)
        soar.post.side_effect = [
            {"success": True, "id": 100},
            {"success": True, "id": 200},
        ]
        mock_soar_client.return_value = soar

        CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "ingest", "--spl", "index=notable"],
        )
        container_body = soar.post.call_args_list[0][1]["body"]
        assert container_body["severity"] == "high"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_notable_preserves_context_fields(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = [_NOTABLE_ROW]

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
                "index=notable",
                "--include-unmapped",
            ],
        )
        art_body = soar.post.call_args_list[1][1]["body"]
        cef = art_body["cef"]
        assert cef.get("event_id") == "EVT-A1B2C3"
        assert cef.get("risk_score") == "85"


class TestIngestSeverityOverride:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_severity_override(
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
                "--severity",
                "low",
            ],
        )
        body = soar.post.call_args_list[0][1]["body"]
        assert body["severity"] == "low"
