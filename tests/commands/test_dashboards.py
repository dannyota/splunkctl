"""Tests for dashboard commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

SAMPLE_XML = "<dashboard><label>Test</label></dashboard>"

ENTRY: dict = {
    "name": "test_dash",
    "acl": {"app": "search"},
    "content": {
        "label": "Test Dashboard",
        "isDashboard": True,
        "isVisible": True,
        "eai:data": SAMPLE_XML,
    },
}


def _mock_resp(entries: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps({"entry": entries}).encode()
    return resp


@patch("splunkctl.commands.dashboards.get_client")
def test_list_dashboards(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([ENTRY])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert data[0]["label"] == "Test Dashboard"


@patch("splunkctl.commands.dashboards.get_client")
def test_list_dashboards_with_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([ENTRY])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list", "--app", "myapp"])
    assert result.exit_code == 0
    path = mock_svc.get.call_args[0][0]
    assert path == "/servicesNS/-/myapp/data/ui/views"


@patch("splunkctl.commands.dashboards.get_client")
def test_get_dashboard(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([ENTRY])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "get", "test_dash"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert SAMPLE_XML in data[0]["eai:data"]


@patch("splunkctl.commands.dashboards.get_client")
def test_get_dashboard_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "get", "missing"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


@patch("splunkctl.commands.dashboards.get_client")
def test_create_dry_run(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    xml_file.write_text(SAMPLE_XML)

    result = CliRunner().invoke(
        cli,
        ["dashboards", "create", "--name", "new", "--file", str(xml_file)],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    mock_gc.return_value.service.post.assert_not_called()


@patch("splunkctl.commands.dashboards.get_client")
def test_create_confirmed(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    xml_file.write_text(SAMPLE_XML)
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "dashboards",
            "create",
            "--name",
            "new",
            "--file",
            str(xml_file),
        ],
    )
    assert result.exit_code == 0
    mock_svc.post.assert_called_once()
    call_path = mock_svc.post.call_args[0][0]
    assert call_path == "/servicesNS/nobody/search/data/ui/views"


@patch("splunkctl.commands.dashboards.get_client")
def test_create_with_label(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    xml_file.write_text(SAMPLE_XML)
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "dashboards",
            "create",
            "--name",
            "new",
            "--file",
            str(xml_file),
            "--label",
            "My Dashboard",
        ],
    )
    assert result.exit_code == 0
    body = mock_svc.post.call_args[1]["body"]
    assert "label=" in body


@patch("splunkctl.commands.dashboards.get_client")
def test_update_dry_run(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    xml_file.write_text(SAMPLE_XML)

    result = CliRunner().invoke(
        cli,
        ["dashboards", "update", "test_dash", "--file", str(xml_file)],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.dashboards.get_client")
def test_update_confirmed(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    xml_file.write_text(SAMPLE_XML)
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "dashboards",
            "update",
            "test_dash",
            "--file",
            str(xml_file),
        ],
    )
    assert result.exit_code == 0
    mock_svc.post.assert_called_once()
    call_path = mock_svc.post.call_args[0][0]
    assert "/test_dash" in call_path


@patch("splunkctl.commands.dashboards.get_client")
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["dashboards", "delete", "test_dash"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.dashboards.get_client")
def test_delete_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "dashboards", "delete", "test_dash"])
    assert result.exit_code == 0
    mock_svc.delete.assert_called_once()
    call_path = mock_svc.delete.call_args[0][0]
    assert "/test_dash" in call_path


@patch("splunkctl.commands.dashboards.get_client")
def test_export_stdout(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([ENTRY])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "test_dash"])
    assert result.exit_code == 0
    assert SAMPLE_XML in result.output


@patch("splunkctl.commands.dashboards.get_client")
def test_export_to_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([ENTRY])
    mock_gc.return_value.service = mock_svc

    out_file = tmp_path / "exported.xml"
    result = CliRunner().invoke(
        cli,
        [
            "dashboards",
            "export",
            "test_dash",
            "--out",
            str(out_file),
        ],
    )
    assert result.exit_code == 0
    assert out_file.read_text() == SAMPLE_XML


@patch("splunkctl.commands.dashboards.get_client")
def test_export_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.get.return_value = _mock_resp([])
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "missing"])
    assert result.exit_code != 0
    assert "not found" in result.stderr
