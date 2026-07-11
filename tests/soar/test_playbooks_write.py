"""Tests for soar playbooks writes — enable, disable, trigger, import, sync."""

from __future__ import annotations

import base64
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

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "splunkctl_seed_noop"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


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


# ─── enable / disable ────────────────────────────────────────────────


class TestPlaybooksEnable:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_enable(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "enable", "10"])
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["active"] is True

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_disable_with_cancel_runs(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "disable",
                "10",
                "--cancel-runs",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["active"] is False
        assert body["cancel_runs"] is True

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_enable_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "playbooks", "enable", "10"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()


# ─── trigger ──────────────────────────────────────────────────────────


class TestPlaybooksTrigger:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_trigger_label(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "trigger",
                "10",
                "--on",
                "label",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["playbook_trigger"] == "label"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_trigger_artifact_created(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "trigger",
                "10",
                "--on",
                "artifact_created",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["playbook_trigger"] == "artifact_created"


# ─── import ───────────────────────────────────────────────────────────


class TestPlaybooksImport:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_from_dir(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 42}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "playbooks", "import", str(FIXTURE_DIR)],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert "playbook" in body
        assert body["scm"] == "local"
        assert body["force"] is True
        # Verify valid base64 -> valid tgz
        raw = base64.b64decode(body["playbook"])
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            names = tar.getnames()
        assert any("splunkctl_seed_noop.json" in n for n in names)
        assert any("splunkctl_seed_noop.py" in n for n in names)

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_from_tgz(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 42}
        mock_cls.return_value = client

        tgz_path = tmp_path / "test.tgz"
        tgz_path.write_bytes(_make_tgz("test_pb"))

        result = CliRunner().invoke(
            cli,
            ["--yes", "soar", "playbooks", "import", str(tgz_path)],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert "playbook" in body

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_with_scm(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 42}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "import",
                str(FIXTURE_DIR),
                "--scm",
                "my_repo",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["scm"] == "my_repo"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "playbooks", "import", str(FIXTURE_DIR)],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_nonexistent_path(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "playbooks",
                "import",
                "/no/such/path",
            ],
        )
        assert result.exit_code == 1

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_no_force(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 42}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "playbooks",
                "import",
                str(FIXTURE_DIR),
                "--no-force",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["force"] is False


# ─── sync ─────────────────────────────────────────────────────────────


class TestPlaybooksSync:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_sync_success(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "playbooks", "sync", "1"])
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["pull"] is True
        assert body["force"] is True

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_sync_local_repo_500(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Local repo returns 500 'Operation not supported'."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "Operation not supported",
            kind="error",
            http_status=500,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "playbooks", "sync", "1"],
        )
        assert result.exit_code == 1
        err = result.stderr.lower()
        assert "local" in err or "not supported" in err

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_sync_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "playbooks", "sync", "1"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()
