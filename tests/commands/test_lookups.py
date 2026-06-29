"""Tests for lookups commands."""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_ENTRIES_JSON = json.dumps(
    {
        "entry": [
            {
                "name": "test_lookup.csv",
                "updated": "2025-01-01T00:00:00+00:00",
                "acl": {"app": "search", "owner": "admin"},
                "content": {
                    "disabled": False,
                    "eai:type": "csv",
                },
            },
            {
                "name": "other.csv",
                "updated": "2025-01-02T00:00:00+00:00",
                "acl": {"app": "SA-Utils", "owner": "nobody"},
                "content": {
                    "disabled": False,
                    "eai:type": "csv",
                },
            },
        ]
    }
).encode()

_SINGLE_ENTRY_JSON = json.dumps(
    {
        "entry": [
            {
                "name": "test_lookup.csv",
                "updated": "2025-01-01T00:00:00+00:00",
                "acl": {"app": "search", "owner": "admin"},
                "content": {
                    "disabled": False,
                    "eai:type": "csv",
                    "eai:data": "host,ip\nweb01,10.0.0.1\n",
                },
            }
        ]
    }
).encode()

_EMPTY_JSON = json.dumps({"entry": []}).encode()


def _mock_response(body: bytes) -> MagicMock:
    resp = MagicMock()
    resp.body = BytesIO(body)
    return resp


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.get.return_value = _mock_response(_ENTRIES_JSON)
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "lookups", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "test_lookup.csv"
    assert parsed[1]["app"] == "SA-Utils"


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups_with_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.get.return_value = _mock_response(_ENTRIES_JSON)
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "lookups", "list", "--app", "search"])
    assert result.exit_code == 0
    mock_svc.service.get.assert_called_once()
    call_args = mock_svc.service.get.call_args
    assert "/search/" in call_args[0][0]


@patch("splunkctl.commands.lookups.get_client")
def test_list_lookups_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.get.return_value = _mock_response(_EMPTY_JSON)
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "lookups", "list"])
    assert result.exit_code == 0
    assert "No lookup tables found" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_get_lookup(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.get.return_value = _mock_response(_SINGLE_ENTRY_JSON)
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "lookups", "get", "test_lookup.csv"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "test_lookup.csv"
    assert "eai:data" in parsed[0]


@patch("splunkctl.commands.lookups.get_client")
def test_get_lookup_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.get.side_effect = Exception("HTTP 404")
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "lookups", "get", "nope.csv"])
    assert "not found" in result.stderr


def test_upload_dry_run(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["lookups", "upload", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "--yes" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_upload_with_yes(mock_gc: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    mock_svc = MagicMock()
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--yes", "lookups", "upload", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "Uploaded" in result.stderr
    mock_svc.service.post.assert_called_once()


def test_update_dry_run(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["lookups", "update", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_update_with_yes(mock_gc: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("host,ip\nweb01,10.0.0.1\n")

    mock_svc = MagicMock()
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--yes", "lookups", "update", "my.csv", "--file", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "Updated" in result.stderr
    mock_svc.service.post.assert_called_once()


def test_delete_dry_run() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["lookups", "delete", "my.csv"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.lookups.get_client")
def test_delete_with_yes(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "lookups", "delete", "my.csv"])
    assert result.exit_code == 0
    assert "Deleted" in result.stderr
    mock_svc.service.delete.assert_called_once()


@patch("splunkctl.commands.lookups.get_client")
def test_download_to_stdout(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    csv_bytes = b"host,ip\nweb01,10.0.0.1\n"
    mock_svc.service.jobs.oneshot.return_value.read.return_value = csv_bytes
    mock_gc.return_value = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["lookups", "download", "test_lookup.csv"])
    assert result.exit_code == 0
    assert "host,ip" in result.output
    assert "web01" in result.output


@patch("splunkctl.commands.lookups.get_client")
def test_download_to_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_svc = MagicMock()
    csv_bytes = b"host,ip\nweb01,10.0.0.1\n"
    mock_svc.service.jobs.oneshot.return_value.read.return_value = csv_bytes
    mock_gc.return_value = mock_svc

    out_file = tmp_path / "out.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["lookups", "download", "test_lookup.csv", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text()
    assert "host,ip" in content
