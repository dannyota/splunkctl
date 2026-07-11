"""Tests for map-file contains extraction, --map help text, and preview unmapped."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.commands.soar._ingest_helpers import (
    ContainerGroup,
    build_preview,
    load_map_file,
)
from splunkctl.main import cli
from splunkctl.soar.cimcef import CEF_CONTAINS_MAP, auto_cef_types, row_to_cef
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
PATCH_SOAR_CLIENT = "splunkctl.commands.soar.ingest.get_soar_client"
PATCH_FETCH = "splunkctl.commands.soar.ingest.fetch_spl_results"


# ---------------------------------------------------------------------------
# Issue 1 — load_map_file returns per-field contains
# ---------------------------------------------------------------------------


class TestLoadMapFileContains:
    """Map-file with custom contains feeds cef_types."""

    def test_custom_contains_returned(self, tmp_path: Path) -> None:
        mapfile = tmp_path / "map.yaml"
        mapfile.write_text(
            textwrap.dedent("""\
                mappings:
                  src: {cef: sourceAddress, contains: [ip]}
                  custom_score: {cef: riskScore, contains: [vault id]}
                unmapped: drop
            """)
        )
        cim_map, contains_map, include_unmapped = load_map_file(str(mapfile))
        assert cim_map == {"src": "sourceAddress", "custom_score": "riskScore"}
        assert contains_map["sourceAddress"] == ["ip"]
        assert contains_map["riskScore"] == ["vault id"]
        assert not include_unmapped

    def test_no_contains_returns_empty(self, tmp_path: Path) -> None:
        mapfile = tmp_path / "map.yaml"
        mapfile.write_text(
            textwrap.dedent("""\
                mappings:
                  src: {cef: sourceAddress}
                unmapped: pass
            """)
        )
        _, contains_map, include_unmapped = load_map_file(str(mapfile))
        assert contains_map == {}
        assert include_unmapped

    def test_custom_contains_merged_over_builtin(self, tmp_path: Path) -> None:
        """Map-file contains overrides built-in for same key."""
        mapfile = tmp_path / "map.yaml"
        mapfile.write_text(
            textwrap.dedent("""\
                mappings:
                  src: {cef: sourceAddress, contains: [ip, host name, custom]}
                  custom_score: {cef: riskScore, contains: [vault id]}
                unmapped: drop
            """)
        )
        _, file_contains, _ = load_map_file(str(mapfile))
        merged = {**CEF_CONTAINS_MAP, **file_contains}

        # Custom overrides built-in sourceAddress
        assert merged["sourceAddress"] == ["ip", "host name", "custom"]
        # Custom new key
        assert merged["riskScore"] == ["vault id"]
        # Built-in keys still present
        assert "destinationPort" in merged
        assert "port" in merged["destinationPort"]

    def test_artifact_cef_types_carry_custom_contains(self, tmp_path: Path) -> None:
        """End-to-end: map-file contains -> auto_cef_types on the artifact."""
        mapfile = tmp_path / "map.yaml"
        mapfile.write_text(
            textwrap.dedent("""\
                mappings:
                  src: {cef: sourceAddress, contains: [ip]}
                  custom_score: {cef: riskScore, contains: [vault id]}
                unmapped: drop
            """)
        )
        cim_map, file_contains, _ = load_map_file(str(mapfile))
        merged = {**CEF_CONTAINS_MAP, **file_contains}

        row: dict[str, Any] = {"src": "10.0.0.1", "custom_score": "42"}
        cef = row_to_cef(row, cim_map=cim_map)
        types = auto_cef_types(cef, contains_map=merged)

        assert types["sourceAddress"] == ["ip"]
        assert types["riskScore"] == ["vault id"]

    def test_builtin_keys_still_resolve_without_mapfile(self) -> None:
        """Built-in CEF_CONTAINS_MAP works unchanged for known keys."""
        cef = {"sourceAddress": "10.0.0.1", "destinationPort": "443"}
        types = auto_cef_types(cef)
        assert "ip" in types["sourceAddress"]
        assert "port" in types["destinationPort"]


# ---------------------------------------------------------------------------
# Issue 2 — --map help text direction
# ---------------------------------------------------------------------------


class TestMapHelpText:
    """--map help string documents the CEF_KEY=SPLUNK_FIELD form."""

    def test_map_help_shows_correct_direction(self) -> None:
        result = CliRunner().invoke(cli, ["soar", "ingest", "--help"])
        assert "CEF_KEY=SPLUNK_FIELD" in result.output


# ---------------------------------------------------------------------------
# Issue 3 — preview honours --include-unmapped
# ---------------------------------------------------------------------------


class TestPreviewIncludeUnmapped:
    """build_preview passes include_unmapped to row_to_cef."""

    def test_unmapped_field_in_preview(self) -> None:
        grp = ContainerGroup("test", "medium", "sdi-1")
        grp.rows = [{"src": "10.0.0.1", "custom_extra": "hello"}]
        cim_map: dict[str, str] = {"src": "sourceAddress"}
        preview = build_preview({"g": grp}, cim_map, include_unmapped=True)
        parsed_cef = json.loads(preview.split("Sample CEF payload:\n")[1])
        assert "custom_extra" in parsed_cef

    def test_unmapped_field_excluded_by_default(self) -> None:
        grp = ContainerGroup("test", "medium", "sdi-1")
        grp.rows = [{"src": "10.0.0.1", "custom_extra": "hello"}]
        cim_map: dict[str, str] = {"src": "sourceAddress"}
        preview = build_preview({"g": grp}, cim_map)
        parsed_cef = json.loads(preview.split("Sample CEF payload:\n")[1])
        assert "custom_extra" not in parsed_cef

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_SOAR_CLIENT)
    @patch(PATCH_FETCH)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_dry_run_preview_includes_unmapped_field(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_fetch: MagicMock,
        mock_soar_client: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        mock_fetch.return_value = [
            {"src": "10.0.0.1", "custom_extra": "hello", "_time": "now", "source": "t"},
        ]
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "ingest",
                "--spl",
                "| makeresults",
                "--include-unmapped",
            ],
        )
        assert result.exit_code == 0
        assert "custom_extra" in result.stderr
