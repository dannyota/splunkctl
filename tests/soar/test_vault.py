"""Tests for soar vault — list, get, upload, download, delete."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_GUARD_SOAR = "splunkctl.commands.soar.vault.soar_check"


# ---------------------------------------------------------------------------
# Vault list
# ---------------------------------------------------------------------------
class TestVaultList:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_default(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Bare list returns vault items."""
        mock_resolve.return_value = soar_cfg()
        items: dict[str, Any] = {
            "count": 2,
            "num_pages": 1,
            "data": [
                {
                    "id": 1,
                    "vault_id": "abc123sha1",
                    "file_name": "malware.exe",
                    "size": 1024,
                    "container": 5,
                },
                {
                    "id": 2,
                    "vault_id": "def456sha1",
                    "file_name": "report.pdf",
                    "size": 2048,
                    "container": 5,
                },
            ],
        }
        client = MagicMock()
        client.get.return_value = items
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "vault", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["vault_id"] == "abc123sha1"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_with_container_filter(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--container passes _filter_container to the API."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        CliRunner().invoke(cli, ["--json", "soar", "vault", "list", "--container", "5"])
        _, kwargs = client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("_filter_container") == "5"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_list_api_error(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """API error exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("forbidden", kind="auth", http_status=401)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "vault", "list"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Vault get
# ---------------------------------------------------------------------------
class TestVaultGet:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_by_vault_id(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """Get a vault document by hash (vault_id)."""
        mock_resolve.return_value = soar_cfg()
        item: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {
                    "id": 1,
                    "hash": "abc123sha1",
                    "names": ["malware.exe"],
                    "size": 1024,
                }
            ],
        }
        client = MagicMock()
        client.get.return_value = item
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "vault", "get", "abc123sha1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["hash"] == "abc123sha1"
        # Verify it queries vault_document with _filter_hash.
        call_args = client.get.call_args
        assert call_args[0][0] == "vault_document"
        params = call_args[1].get("params", {})
        assert params["_filter_hash"] == '"abc123sha1"'

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_get_not_found(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """Nonexistent vault_id exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "vault", "get", "nonexistent"]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Vault upload
# ---------------------------------------------------------------------------
class TestVaultUpload:
    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_upload_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Upload without --yes shows dry-run preview."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = False
        client = MagicMock()
        mock_cls.return_value = client

        f = tmp_path / "test.txt"
        f.write_text("hello")

        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "vault", "upload", "--container", "5", str(f)],
        )
        assert result.exit_code == 0
        client.post.assert_not_called()

    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_upload_applies(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Upload with --yes posts base64 content."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = True
        client = MagicMock()
        client.post.return_value = {
            "success": True,
            "vault_id": "abc123sha1",
            "hash": "abc123sha1",
            "id": 10,
            "size": 5,
        }
        mock_cls.return_value = client

        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "vault",
                "upload",
                "--container",
                "5",
                str(f),
            ],
        )
        assert result.exit_code == 0
        # Verify post was called with base64-encoded content.
        call_args = client.post.call_args
        body = call_args[1]["body"] if "body" in call_args[1] else call_args[0][1]
        assert body["file_content"] == base64.b64encode(b"hello").decode()
        assert body["container_id"] == 5
        assert body["file_name"] == "test.txt"

    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_upload_large_file_warning(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Files >30 MB emit a warning about the nginx cap."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = False
        client = MagicMock()
        mock_cls.return_value = client

        # Create a file just over 30 MB (we'll mock the size check).
        f = tmp_path / "big.bin"
        f.write_bytes(b"x")  # actual file is small; we patch stat

        with patch(
            "splunkctl.commands.soar.vault._file_size_bytes",
            return_value=31 * 1024 * 1024,
        ):
            result = CliRunner().invoke(
                cli,
                ["soar", "vault", "upload", "--container", "5", str(f)],
            )
        # Warning mentions the file size and the nginx cap.
        combined = result.output
        assert "31.0 MB" in combined
        assert "32 MB" in combined

    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_upload_missing_container(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Upload without --container fails."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        f = tmp_path / "test.txt"
        f.write_text("hello")

        result = CliRunner().invoke(cli, ["soar", "vault", "upload", str(f)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Vault download
# ---------------------------------------------------------------------------
class TestVaultDownload:
    @patch("splunkctl.commands.soar.vault.sys")
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_download_to_stdout(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_sys: MagicMock,
    ) -> None:
        """Download without --out writes raw bytes to stdout.buffer."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.return_value = b"file-content-here"
        mock_cls.return_value = client

        buf = MagicMock()
        mock_sys.stdout.buffer = buf

        result = CliRunner().invoke(cli, ["soar", "vault", "download", "abc123sha1"])
        assert result.exit_code == 0
        buf.write.assert_called_once_with(b"file-content-here")

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_download_to_file(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Download with --out writes to the specified file."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.return_value = b"binary-data"
        mock_cls.return_value = client

        out_file = tmp_path / "downloaded.bin"
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "vault",
                "download",
                "abc123sha1",
                "--out",
                str(out_file),
            ],
        )
        assert result.exit_code == 0
        assert out_file.read_bytes() == b"binary-data"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_download_api_error(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """API error on download exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "vault", "download", "nonexistent"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Vault delete
# ---------------------------------------------------------------------------
class TestVaultDelete:
    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dry_run(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Delete without --yes shows dry-run preview."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = False
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "vault", "delete", "42"])
        assert result.exit_code == 0
        client.delete.assert_not_called()

    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_applies(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """Delete with --yes calls container_attachment DELETE."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = True
        client = MagicMock()
        client.delete.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "vault", "delete", "42"])
        assert result.exit_code == 0
        client.delete.assert_called_once_with("container_attachment/42")

    @patch(PATCH_GUARD_SOAR)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_405_explanation(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard: MagicMock,
    ) -> None:
        """405 on delete gives clear explanation about vault_document."""
        mock_resolve.return_value = soar_cfg()
        mock_guard.return_value = True
        client = MagicMock()
        client.delete.side_effect = SOARError("HTTP 405", kind="http", http_status=405)
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--yes", "soar", "vault", "delete", "42"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Client get_bytes
# ---------------------------------------------------------------------------
class TestClientGetBytes:
    def test_get_bytes_returns_raw_content(self) -> None:
        """get_bytes returns raw response content."""
        from splunkctl.soar.client import SOARClient

        client = SOARClient(host="soar.test", token="tok")  # noqa: S106

        import requests

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.content = b"raw-bytes-here"
        mock_resp.headers = {"Content-Type": "application/octet-stream"}

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_bytes(
                "download_attachment", params={"vault_id": "abc123"}
            )
        assert result == b"raw-bytes-here"

    def test_get_bytes_raises_on_error(self) -> None:
        """get_bytes raises SOARError on non-2xx."""
        from splunkctl.soar.client import SOARClient

        client = SOARClient(host="soar.test", token="tok")  # noqa: S106

        import requests

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_resp.content = b"Not Found"
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch.object(client._session, "request", return_value=mock_resp):
            import pytest

            with pytest.raises(SOARError):
                client.get_bytes("download_attachment", params={"vault_id": "missing"})


# ---------------------------------------------------------------------------
# SOAR guard banner + check
# ---------------------------------------------------------------------------
class TestSoarGuard:
    def test_soar_banner_format(self) -> None:
        """soar_banner produces (soar @ host:port) format."""
        from splunkctl.guard import soar_banner

        ctx = MagicMock()
        ctx.obj = {"config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            tag = soar_banner(ctx)
        assert "soar.lab" in tag
        assert "8443" in tag

    def test_soar_check_dry_run(self) -> None:
        """soar_check returns False in dry-run mode."""
        from splunkctl.guard import soar_check

        ctx = MagicMock()
        ctx.obj = {"dry_run": True, "config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            assert soar_check(ctx, "upload file") is False

    def test_soar_check_applies(self) -> None:
        """soar_check returns True with --yes."""
        from splunkctl.guard import soar_check

        ctx = MagicMock()
        ctx.obj = {"dry_run": False, "config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            assert soar_check(ctx, "upload file") is True
