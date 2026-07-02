"""Tests for dashboard commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

SAMPLE_XML = "<dashboard><label>Test</label></dashboard>"


def _mock_dashboard(
    name: str = "test_dash",
    app: str = "search",
    label: str = "Test Dashboard",
    xml: str = SAMPLE_XML,
) -> MagicMock:
    d = MagicMock()
    d.name = name
    d.access = MagicMock()
    d.access.app = app
    d.content = {
        "label": label,
        "isDashboard": True,
        "isVisible": True,
        "eai:data": xml,
    }
    d.export.return_value = xml
    return d


@patch("splunkctl.commands.dashboards.get_client")
def test_list_dashboards(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert data[0]["label"] == "Test Dashboard"


@patch("splunkctl.commands.dashboards.get_client")
def test_list_dashboards_with_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list", "--app", "myapp"])
    assert result.exit_code == 0
    mock_svc.dashboards.list.assert_called_once_with(app="myapp", owner="-")


@patch("splunkctl.commands.dashboards.get_client")
def test_get_dashboard(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "get", "test_dash"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert SAMPLE_XML in data[0]["eai:data"]


@patch("splunkctl.commands.dashboards.get_client")
def test_get_dashboard_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = []
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
    mock_gc.return_value.service.dashboards.create.assert_not_called()


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
    mock_svc.dashboards.create.assert_called_once()
    args, kwargs = mock_svc.dashboards.create.call_args
    assert args[0] == "new"
    assert args[1] == SAMPLE_XML
    assert kwargs["app"] == "search"


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
    dash = _mock_dashboard()
    mock_svc.dashboards.list.return_value = [dash]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--yes", "dashboards", "update", "test_dash", "--file", str(xml_file)],
    )
    assert result.exit_code == 0
    dash.update.assert_called_once()


@patch("splunkctl.commands.dashboards.get_client")
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["dashboards", "delete", "test_dash"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch("splunkctl.commands.dashboards.get_client")
def test_delete_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    dash = _mock_dashboard()
    mock_svc.dashboards.list.return_value = [dash]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--yes", "dashboards", "delete", "test_dash"])
    assert result.exit_code == 0
    dash.delete.assert_called_once()


@patch("splunkctl.commands.dashboards.get_client")
def test_export_stdout(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "test_dash"])
    assert result.exit_code == 0
    assert SAMPLE_XML in result.output


@patch("splunkctl.commands.dashboards.get_client")
def test_export_to_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    out_file = tmp_path / "exported.xml"
    result = CliRunner().invoke(
        cli,
        ["dashboards", "export", "test_dash", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    assert out_file.read_text() == SAMPLE_XML


@patch("splunkctl.commands.dashboards.get_client")
def test_export_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "missing"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


@patch("splunkctl.commands.dashboards.get_client")
def test_list_app_filters_rows(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [
        _mock_dashboard("mine", app="search"),
        _mock_dashboard("alert_view", app="system"),
    ]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--json", "dashboards", "list", "--app", "search"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [d["app"] for d in data] == ["search"]


@patch("splunkctl.commands.dashboards.get_client")
def test_list_excludes_non_dashboards_by_default(mock_gc: MagicMock) -> None:
    view = _mock_dashboard("nav_thing")
    view.content = {**view.content, "isDashboard": "0"}
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard("real"), view]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert [d["name"] for d in json.loads(result.output)] == ["real"]

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list", "--all"])
    assert [d["name"] for d in json.loads(result.output)] == ["real", "nav_thing"]
