"""Tests for soar lists — reads: list, get, export, helpers."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
class TestListsList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "blocklist", "content": [["a"]]},
                {"id": 2, "name": "allowlist", "content": [["b"]]},
            ],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "lists", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "blocklist"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth", http_status=401)
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "lists", "list"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------
class TestListsGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_id(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "blocklist",
            "content": [["col1", "col2"], ["a", "b"]],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "lists", "get", "1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "blocklist"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_name(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        """Non-numeric argument triggers name lookup."""
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = [
            {
                "count": 1,
                "num_pages": 1,
                "data": [{"id": 5, "name": "blocklist"}],
            },
            {"id": 5, "name": "blocklist", "content": [["x"]]},
        ]
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "lists", "get", "blocklist"]
        )
        assert result.exit_code == 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_name_not_found(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli, ["--json", "soar", "lists", "get", "nonexistent"]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
class TestListsExport:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_json(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "id": 1,
            "name": "test",
            "content": [["h1", "h2"], ["a", "b"]],
        }
        mock_cls.return_value = client
        result = CliRunner().invoke(cli, ["--json", "soar", "lists", "export", "1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == [["h1", "h2"], ["a", "b"]]

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_csv(self, mock_res: MagicMock, mock_cls: MagicMock) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.return_value = b"h1,h2\r\na,b\r\n"
        mock_cls.return_value = client
        result = CliRunner().invoke(
            cli,
            ["soar", "lists", "export", "1", "--format", "csv"],
        )
        assert result.exit_code == 0
        reader = csv.reader(io.StringIO(result.output))
        rows = list(reader)
        assert rows[0] == ["h1", "h2"]
        assert rows[1] == ["a", "b"]

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_csv_to_file(
        self,
        mock_res: MagicMock,
        mock_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_res.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.return_value = b"h1,h2\r\na,b\r\n"
        mock_cls.return_value = client
        out = tmp_path / "out.csv"
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "lists",
                "export",
                "1",
                "--format",
                "csv",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert out.exists()
        assert "h1,h2" in out.read_text()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class TestParseContent:
    def test_parse_json_file(self, tmp_path: Path) -> None:
        from splunkctl.commands.soar.lists import _parse_content_file

        f = tmp_path / "data.json"
        f.write_text(json.dumps([["a", "b"], ["c", "d"]]))
        rows = _parse_content_file(f)
        assert rows == [["a", "b"], ["c", "d"]]

    def test_parse_csv_file(self, tmp_path: Path) -> None:
        from splunkctl.commands.soar.lists import _parse_content_file

        f = tmp_path / "data.csv"
        f.write_text("h1,h2\na,b\n")
        rows = _parse_content_file(f)
        assert rows == [["h1", "h2"], ["a", "b"]]

    def test_parse_invalid_json(self, tmp_path: Path) -> None:
        from splunkctl.commands.soar.lists import _parse_content_file

        f = tmp_path / "bad.json"
        f.write_text("{not an array}")
        with pytest.raises(click.UsageError):
            _parse_content_file(f)
