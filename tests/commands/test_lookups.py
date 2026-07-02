"""Tests for lookups commands."""

import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_lookup(
    name: str = "test_lookup.csv",
    app: str = "search",
    owner: str = "admin",
) -> MagicMock:
    lk = MagicMock()
    lk.name = name
    lk.access = MagicMock()
    lk.access.app = app
    lk.access.owner = owner
    lk.content = {
        "disabled": False,
        "eai:type": "csv",
        "eai:data": "host,ip\nweb01,10.0.0.1\n",
    }
    return lk


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = [
        _mock_lookup(),
        _mock_lookup(name="other.csv", app="SA-Utils", owner="nobody"),
    ]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "lookups", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "test_lookup.csv"
    assert parsed[1]["app"] == "SA-Utils"


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups_with_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = [_mock_lookup()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "lookups", "list", "--app", "search"])
    assert result.exit_code == 0
    mock_svc.lookup_table_files.list.assert_called_once_with(app="search", owner="-")


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "lookups", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"

    result = CliRunner().invoke(cli, ["--format", "table", "lookups", "list"])
    assert result.exit_code == 0
    assert "No lookup tables found" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_get_lookup(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = [_mock_lookup()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "lookups", "get", "test_lookup.csv"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "test_lookup.csv"
    assert "eai:data" in parsed[0]


@patch("splunkctl.commands.lookups.get_client")
def test_get_lookup_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "lookups", "get", "nope.csv"])
    assert "not found" in result.stderr


def test_upload_dry_run(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    result = CliRunner().invoke(
        cli, ["lookups", "upload", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "--yes" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_upload_with_yes(mock_gc: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    mock_client = MagicMock()
    mock_gc.return_value = mock_client

    result = CliRunner().invoke(
        cli, ["--yes", "lookups", "upload", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "Uploaded" in result.stderr
    mock_client.upload_lookup.assert_called_once_with("my.csv", ANY, app="search")


def test_update_dry_run(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    result = CliRunner().invoke(
        cli, ["lookups", "update", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_update_with_yes(mock_gc: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    mock_client = MagicMock()
    mock_gc.return_value = mock_client

    result = CliRunner().invoke(
        cli, ["--yes", "lookups", "update", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "Updated" in result.stderr
    mock_client.upload_lookup.assert_called_once_with(
        "my.csv", ANY, app="search", update=True
    )


def test_delete_dry_run() -> None:
    result = CliRunner().invoke(cli, ["lookups", "delete", "my.csv"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_delete_with_yes(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    lk = _mock_lookup()
    mock_svc.lookup_table_files.list.return_value = [lk]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "lookups", "delete", "my.csv"])
    assert result.exit_code == 0
    assert "Deleted" in result.stderr
    lk.delete.assert_called_once()


@patch("splunkctl.commands.lookups.get_client")
def test_download_to_stdout(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    csv_bytes = b"host,ip\nweb01,10.0.0.1\n"
    mock_svc.jobs.oneshot.return_value.read.return_value = csv_bytes
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["lookups", "download", "test_lookup.csv"])
    assert result.exit_code == 0
    assert "host,ip" in result.output
    assert "web01" in result.output


@patch("splunkctl.commands.lookups.get_client")
def test_download_to_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_svc = MagicMock()
    csv_bytes = b"host,ip\nweb01,10.0.0.1\n"
    mock_svc.jobs.oneshot.return_value.read.return_value = csv_bytes
    mock_gc.return_value.service = mock_svc

    out_file = tmp_path / "out.csv"
    result = CliRunner().invoke(
        cli,
        ["lookups", "download", "test_lookup.csv", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text()
    assert "host,ip" in content


@patch("splunkctl.commands.lookups.get_client")
def test_download_missing_lookup_fails(mock_gc: MagicMock, tmp_path) -> None:
    mock_svc = MagicMock()
    mock_svc.lookup_table_files.list.return_value = []
    mock_gc.return_value.service = mock_svc

    out = tmp_path / "x.csv"
    result = CliRunner().invoke(
        cli, ["lookups", "download", "ghost.csv", "--app", "search", "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "not found" in result.stderr
    assert not out.exists()
    mock_svc.jobs.oneshot.assert_not_called()
