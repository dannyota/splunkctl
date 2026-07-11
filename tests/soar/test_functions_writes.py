"""Tests for soar functions — import, export, update, delete (write-side)."""

from __future__ import annotations

import base64
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_GUARD_SOAR = "splunkctl.commands.soar.functions.soar_check"


def _make_tgz(files: dict[str, str]) -> bytes:
    """Build an in-memory tgz with the given name->content pairs."""
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Functions import
# ---------------------------------------------------------------------------
class TestFunctionsImport:
    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_tgz(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Import a .tgz custom function bundle."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 99}
        mock_cls.return_value = client

        tgz_path = tmp_path / "identity.tgz"
        tgz_path.write_bytes(
            _make_tgz(
                {
                    "identity.json": '{"name":"identity"}',
                    "identity.py": "def main():\n    pass\n",
                }
            )
        )

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "functions", "import", str(tgz_path)],
        )
        assert result.exit_code == 0
        call_args = client.post.call_args
        assert call_args[0][0] == "import_custom_function"
        body = call_args[1]["body"]
        assert "custom_function" in body
        assert body.get("scm") == "local"
        assert body.get("force") is True

    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_directory(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Import from a directory — auto-creates tgz."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 100}
        mock_cls.return_value = client

        func_dir = tmp_path / "my_func"
        func_dir.mkdir()
        (func_dir / "my_func.json").write_text('{"name":"my_func"}')
        (func_dir / "my_func.py").write_text("def main():\n    pass\n")

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "functions", "import", str(func_dir)],
        )
        assert result.exit_code == 0
        call_args = client.post.call_args
        assert call_args[0][0] == "import_custom_function"
        body = call_args[1]["body"]
        b64_data = body["custom_function"]
        raw = base64.b64decode(b64_data)
        with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as tf:
            names = tf.getnames()
        assert any("my_func.json" in n for n in names)
        assert any("my_func.py" in n for n in names)

    @patch(PATCH_GUARD_SOAR, return_value=False)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_dryrun(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Dry-run skips the actual import."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        tgz_path = tmp_path / "func.tgz"
        tgz_path.write_bytes(_make_tgz({"func.json": "{}", "func.py": "pass"}))

        result = CliRunner().invoke(
            cli, ["--json", "soar", "functions", "import", str(tgz_path)]
        )
        assert result.exit_code == 0
        client.post.assert_not_called()

    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_import_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """API error on import exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.side_effect = SOARError(
            "import failed", kind="error", http_status=400
        )
        mock_cls.return_value = client

        tgz_path = tmp_path / "bad.tgz"
        tgz_path.write_bytes(_make_tgz({"bad.json": "{}", "bad.py": "pass"}))

        result = CliRunner().invoke(
            cli,
            ["--json", "--yes", "soar", "functions", "import", str(tgz_path)],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Functions export
# ---------------------------------------------------------------------------
class TestFunctionsExport:
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_to_file(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Export writes tgz to --out file."""
        mock_resolve.return_value = soar_cfg()
        tgz_data = _make_tgz({"fn.json": "{}", "fn.py": "pass"})
        client = MagicMock()
        client.get_bytes.return_value = tgz_data
        mock_cls.return_value = client

        out_file = tmp_path / "export.tgz"
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "functions",
                "export",
                "1",
                "--out",
                str(out_file),
            ],
        )
        assert result.exit_code == 0
        assert out_file.read_bytes() == tgz_data

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_to_stdout(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
    ) -> None:
        """Export sends raw bytes to stdout when --out is omitted."""
        mock_resolve.return_value = soar_cfg()
        tgz_data = _make_tgz({"fn.json": "{}", "fn.py": "pass"})
        client = MagicMock()
        client.get_bytes.return_value = tgz_data
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["soar", "functions", "export", "1"])
        assert result.exit_code == 0
        client.get_bytes.assert_called_once_with("custom_function/1/export", params={})
        assert result.output_bytes == tgz_data

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_export_api_error(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """API error on export exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get_bytes.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "functions", "export", "999"]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Functions update
# ---------------------------------------------------------------------------
class TestFunctionsUpdate:
    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_python(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Update replaces python source and commit message."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        scm_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 1, "name": "local"}],
        }
        func_resp: dict[str, Any] = {
            "id": 42,
            "name": "format_ip",
            "python": "def main():\n    pass\n",
            "module": "format_ip",
            "scm_id": 1,
            "draft_mode": False,
        }
        client.get.side_effect = [scm_resp, func_resp]
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        py_file = tmp_path / "new_code.py"
        py_file.write_text("def main():\n    return 'updated'\n")

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "functions",
                "update",
                "42",
                "--python",
                str(py_file),
                "--message",
                "update logic",
            ],
        )
        assert result.exit_code == 0
        call_args = client.post.call_args
        assert call_args[0][0] == "custom_function/42"
        body = call_args[1]["body"]
        assert "return 'updated'" in body["python"]
        assert body["commit_message"] == "update logic"
        assert body["scm_id"] == 1

    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_scm_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Update fails if no SCM repo is found."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        py_file = tmp_path / "code.py"
        py_file.write_text("pass")

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "functions",
                "update",
                "1",
                "--python",
                str(py_file),
                "--message",
                "test",
            ],
        )
        assert result.exit_code != 0

    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_python_version_27_upgrade(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Legacy python_version 2.7 is upgraded to 3 with a warning."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        scm_resp: dict[str, Any] = {
            "count": 1,
            "num_pages": 1,
            "data": [{"id": 1, "name": "local"}],
        }
        func_resp: dict[str, Any] = {
            "id": 50,
            "name": "old_func",
            "python": "def main():\n    pass\n",
            "module": "old_func",
            "python_version": "2.7",
            "draft_mode": False,
        }
        client.get.side_effect = [scm_resp, func_resp]
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        py_file = tmp_path / "code.py"
        py_file.write_text("def main():\n    return 'v3'\n")

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "functions",
                "update",
                "50",
                "--python",
                str(py_file),
                "--message",
                "upgrade test",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["python_version"] == "3"
        assert "upgrading python_version 2.7 -> 3" in (result.stderr or "")

    @patch(PATCH_GUARD_SOAR, return_value=False)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dryrun(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Dry-run skips the actual update."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        py_file = tmp_path / "code.py"
        py_file.write_text("pass")

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "functions",
                "update",
                "1",
                "--python",
                str(py_file),
                "--message",
                "test",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Functions delete
# ---------------------------------------------------------------------------
class TestFunctionsDelete:
    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_by_id(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
    ) -> None:
        """Delete a custom function by id."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.return_value = {"id": 42, "success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "functions", "delete", "42"]
        )
        assert result.exit_code == 0
        client.delete.assert_called_once_with("custom_function/42")

    @patch(PATCH_GUARD_SOAR, return_value=False)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_dryrun(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
    ) -> None:
        """Dry-run skips the actual delete."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "functions", "delete", "42"]
        )
        assert result.exit_code == 0
        client.delete.assert_not_called()

    @patch(PATCH_GUARD_SOAR, return_value=True)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_delete_api_error(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        _guard: MagicMock,
    ) -> None:
        """API error on delete exits 1."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.delete.side_effect = SOARError(
            "not found", kind="not_found", http_status=404
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "--yes", "soar", "functions", "delete", "999"]
        )
        assert result.exit_code != 0
