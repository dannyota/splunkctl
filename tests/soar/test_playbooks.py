"""Tests for soar playbooks reads — list, get, export, repos."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


def _playbook_data(
    *,
    pb_id: int = 10,
    name: str = "test_pb",
    active: bool = True,
    draft_mode: bool = False,
) -> dict[str, Any]:
    return {
        "id": pb_id,
        "name": name,
        "active": active,
        "draft_mode": draft_mode,
        "playbook_type": "automation",
        "labels": ["events"],
        "category": "Uncategorized",
        "version": 1,
    }


def _make_tgz(name: str = "splunkctl_seed_noop") -> bytes:
    """Build a minimal tgz bundle in memory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        json_content = json.dumps({"name": name}).encode()
        info = tarfile.TarInfo(name=f"{name}/{name}.json")
        info.size = len(json_content)
        tar.addfile(info, io.BytesIO(json_content))

        py_content = b"# noop\n"
        info2 = tarfile.TarInfo(name=f"{name}/{name}.py")
        info2.size = len(py_content)
        tar.addfile(info2, io.BytesIO(py_content))
    return buf.getvalue()


# ─── list ─────────────────────────────────────────────────────────────


class TestPlaybooksList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_basic(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_playbook_data()],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "playbooks", "list"])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert len(rows) == 1
        assert rows[0]["name"] == "test_pb"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_active_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "playbooks", "list", "--active"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1].get("params", {})
        assert params.get("_filter_active") == "True"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_label_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "playbooks", "list", "--label", "events"],
        )
        assert result.exit_code == 0
        params = client.get.call_args[1].get("params", {})
        assert '"events"' in params.get("_filter_labels__contains", "")

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_repo_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "playbooks", "list", "--repo", "local"],
        )
        assert result.exit_code == 0
        params = client.get.call_args[1].get("params", {})
        assert '"local"' in params.get("_filter_scm", "")


# ─── get ──────────────────────────────────────────────────────────────


class TestPlaybooksGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_id(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _playbook_data(pb_id=10)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "playbooks", "get", "10"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == 10
        client.get.assert_called_once_with("playbook/10", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "playbooks", "get", "999"])
        assert result.exit_code == 1


# ─── export ───────────────────────────────────────────────────────────


class TestPlaybooksExport:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_tgz_to_stdout(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        tgz = _make_tgz("test_pb")
        client.get_bytes.return_value = tgz
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "playbooks", "export", "10"])
        assert result.exit_code == 0
        client.get_bytes.assert_called_once_with("playbook/10/export", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_unpack(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        tgz = _make_tgz("test_pb")
        client.get_bytes.return_value = tgz
        mock_cls.return_value = client

        out_dir = str(tmp_path)
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "playbooks",
                "export",
                "10",
                "--unpack",
                "--out",
                out_dir,
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "test_pb" / "test_pb.json").exists()
        assert (tmp_path / "test_pb" / "test_pb.py").exists()

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_by_name(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Non-numeric identifier triggers name lookup."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_playbook_data(pb_id=10, name="my_pb")],
        }
        tgz = _make_tgz("my_pb")
        client.get_bytes.return_value = tgz
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "playbooks", "export", "my_pb"])
        assert result.exit_code == 0
        client.get_bytes.assert_called_once_with("playbook/10/export", params={})

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_name_not_found(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 0,
            "num_pages": 1,
            "data": [],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "playbooks", "export", "nonexistent"],
        )
        assert result.exit_code == 1


# ─── repos ────────────────────────────────────────────────────────────


class TestPlaybooksRepos:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_repos_list(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {
                    "id": 1,
                    "name": "local",
                    "uri": "file:////opt/phantom/scm/git/local",
                    "read_only": False,
                }
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "playbooks", "repos"])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert rows[0]["name"] == "local"
        client.get.assert_called_once_with("scm", params={})
