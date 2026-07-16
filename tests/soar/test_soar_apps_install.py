"""Tests for soar apps install/uninstall (guarded mutations)."""

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

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


def _make_app_tgz(name: str = "myapp") -> bytes:
    """Build a minimal app tgz in memory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        content = json.dumps({"app_name": name}).encode()
        info = tarfile.TarInfo(name=f"{name}/app.json")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


# ─── install ─────────────────────────────────────────────────────────


class TestAppsInstall:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_install_success(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"id": 99, "name": "myapp"}
        mock_cls.return_value = client

        tgz_path = tmp_path / "myapp.tgz"
        tgz_path.write_bytes(_make_app_tgz())

        result = CliRunner().invoke(
            cli, ["--yes", "soar", "apps", "install", str(tgz_path)]
        )
        assert result.exit_code == 0
        assert "99" in result.output or "99" in result.stderr
        # Verify the body carries the base64-encoded tgz
        body = client.post.call_args[1]["body"]
        assert "app" in body

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_install_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        tgz_path = tmp_path / "myapp.tgz"
        tgz_path.write_bytes(_make_app_tgz())

        result = CliRunner().invoke(cli, ["soar", "apps", "install", str(tgz_path)])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_install_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "Invalid app package", kind="error", http_status=400
        )
        mock_cls.return_value = client

        tgz_path = tmp_path / "bad.tgz"
        tgz_path.write_bytes(_make_app_tgz())

        result = CliRunner().invoke(
            cli, ["--yes", "--json", "soar", "apps", "install", str(tgz_path)]
        )
        assert result.exit_code == 1

    def test_install_nonexistent_path(self) -> None:
        result = CliRunner().invoke(
            cli, ["--yes", "soar", "apps", "install", "/no/such/file.tgz"]
        )
        # Click's exists=True on the path argument rejects before reaching cmd
        assert result.exit_code == 2


# ─── uninstall ───────────────────────────────────────────────────────


class TestAppsUninstall:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "apps", "uninstall", "42"])
        assert result.exit_code == 0
        client.delete.assert_called_once_with("app/42")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_by_name(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 7, "name": "DNS"}],
        }
        client.delete.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "apps", "uninstall", "DNS"])
        assert result.exit_code == 0
        client.delete.assert_called_once_with("app/7")

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_not_found(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "--json", "soar", "apps", "uninstall", "NoSuchApp"]
        )
        assert result.exit_code == 1
        client.delete.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_ambiguous(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {"id": 1, "name": "DNS"},
                {"id": 2, "name": "DNS"},
            ],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "--json", "soar", "apps", "uninstall", "DNS"]
        )
        assert result.exit_code == 1
        client.delete.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "apps", "uninstall", "42"])
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.delete.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_uninstall_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        mock_resolve.return_value = _WRITE_CFG
        mock_guard.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "delete requires username/password credentials",
            kind="auth",
            http_status=None,
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--yes", "--json", "soar", "apps", "uninstall", "42"]
        )
        assert result.exit_code == 1
