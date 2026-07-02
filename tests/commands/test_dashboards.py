"""Tests for dashboard commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.dashboards.get_client"
SAMPLE_XML = "<dashboard><label>Test</label></dashboard>"
STUDIO_XML = (
    '<dashboard version="2" theme="light">'
    "<label>Studio</label>"
    '<definition><![CDATA[{"viz": "bar"}]]></definition>'
    "</dashboard>"
)


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


@patch(_PATCH)
def test_list_dashboards(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert data[0]["label"] == "Test Dashboard"


@patch(_PATCH)
def test_list_dashboards_with_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--json", "dashboards", "list", "--app", "myapp"],
    )
    assert result.exit_code == 0
    mock_svc.dashboards.list.assert_called_once_with(app="myapp", owner="-")


@patch(_PATCH)
def test_list_type_column(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [
        _mock_dashboard("classic_dash"),
        _mock_dashboard("studio_dash", xml=STUDIO_XML),
    ]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["type"] == "classic"
    assert data[1]["type"] == "studio"


@patch(_PATCH)
def test_get_dashboard(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "get", "test_dash"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "test_dash"
    assert SAMPLE_XML in data[0]["eai:data"]


@patch(_PATCH)
def test_get_definition_studio(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    d = _mock_dashboard("studio_dash", xml=STUDIO_XML)
    mock_svc.dashboards.list.return_value = [d]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["dashboards", "get", "studio_dash", "--definition"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["viz"] == "bar"


@patch(_PATCH)
def test_get_definition_classic_errors(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["dashboards", "get", "test_dash", "--definition"],
    )
    assert result.exit_code != 0
    assert "Not a Studio" in result.stderr


@patch(_PATCH)
def test_get_dashboard_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "get", "missing"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


@patch(_PATCH)
def test_get_dashboard_not_found_json_envelope(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "get", "missing"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"


@patch(_PATCH)
def test_create_validates_broken_xml(mock_gc: MagicMock, tmp_path: Path) -> None:
    bad = tmp_path / "broken.xml"
    bad.write_text("<dashboard><unclosed>")

    result = CliRunner().invoke(
        cli,
        ["dashboards", "create", "--name", "x", "--file", str(bad)],
    )
    assert result.exit_code != 0
    assert "Invalid XML" in result.stderr


@patch(_PATCH)
def test_create_validates_broken_json(mock_gc: MagicMock, tmp_path: Path) -> None:
    bad = tmp_path / "broken.json"
    bad.write_text("{bad json")

    result = CliRunner().invoke(
        cli,
        [
            "dashboards",
            "create",
            "--name",
            "x",
            "--file",
            str(bad),
            "--type",
            "studio",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid JSON" in result.stderr


@patch(_PATCH)
def test_create_studio_wraps_json(mock_gc: MagicMock, tmp_path: Path) -> None:
    f = tmp_path / "viz.json"
    f.write_text('{"viz": "pie"}')
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--yes", "dashboards", "create", "--name", "pie", "--file", str(f)],
    )
    assert result.exit_code == 0
    args, _ = mock_svc.dashboards.create.call_args
    assert 'version="2"' in args[1]
    assert "<label>pie</label>" in args[1]
    assert "CDATA" in args[1]


@patch(_PATCH)
def test_create_with_sharing(mock_gc: MagicMock, tmp_path: Path) -> None:
    f = tmp_path / "dash.xml"
    f.write_text(SAMPLE_XML)
    client = mock_gc.return_value
    client.service.dashboards.create.return_value = MagicMock()

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "dashboards",
            "create",
            "--name",
            "shared",
            "--file",
            str(f),
            "--sharing",
            "app",
        ],
    )
    assert result.exit_code == 0
    client.set_acl.assert_called_once()
    assert client.set_acl.call_args.kwargs["sharing"] == "app"


@patch(_PATCH)
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


@patch(_PATCH)
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


@patch(_PATCH)
def test_update_shows_diff(mock_gc: MagicMock, tmp_path: Path) -> None:
    xml_file = tmp_path / "dash.xml"
    new_xml = "<dashboard><label>Updated</label></dashboard>"
    xml_file.write_text(new_xml)
    mock_svc = MagicMock()
    d = _mock_dashboard()
    mock_svc.dashboards.list.return_value = [d]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["dashboards", "update", "test_dash", "--file", str(xml_file)],
    )
    assert result.exit_code == 0
    assert "---" in result.stderr or "+++" in result.stderr


@patch(_PATCH)
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


@patch(_PATCH)
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["dashboards", "delete", "test_dash"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


@patch(_PATCH)
def test_delete_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    dash = _mock_dashboard()
    mock_svc.dashboards.list.return_value = [dash]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--yes", "dashboards", "delete", "test_dash"],
    )
    assert result.exit_code == 0
    dash.delete.assert_called_once()


@patch(_PATCH)
def test_export_stdout(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard()]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "test_dash"])
    assert result.exit_code == 0
    assert SAMPLE_XML in result.output


@patch(_PATCH)
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


@patch(_PATCH)
def test_export_definition(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    d = _mock_dashboard("studio", xml=STUDIO_XML)
    mock_svc.dashboards.list.return_value = [d]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["dashboards", "export", "studio", "--definition"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["viz"] == "bar"


@patch(_PATCH)
def test_export_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = []
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["dashboards", "export", "missing"])
    assert result.exit_code != 0
    assert "not found" in result.stderr


@patch(_PATCH)
def test_export_all_writes_files(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [
        _mock_dashboard("d1", app="search"),
        _mock_dashboard("d2", app="myapp"),
    ]
    mock_gc.return_value.service = mock_svc

    out_dir = tmp_path / "export"
    result = CliRunner().invoke(
        cli,
        ["dashboards", "export", "--all", "--dir", str(out_dir)],
    )
    assert result.exit_code == 0
    assert (out_dir / "search" / "d1.xml").exists()
    assert (out_dir / "myapp" / "d2.xml").exists()
    assert "2 dashboard(s)" in result.stderr


@patch(_PATCH)
def test_export_all_needs_dir(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["dashboards", "export", "--all"])
    assert result.exit_code != 0
    assert "--dir" in result.stderr


@patch(_PATCH)
def test_share_dashboard(mock_gc: MagicMock) -> None:
    client = mock_gc.return_value
    d = _mock_dashboard()
    client.service.dashboards.list.return_value = [d]

    result = CliRunner().invoke(
        cli,
        ["--yes", "dashboards", "share", "test_dash", "--sharing", "app"],
    )
    assert result.exit_code == 0
    client.set_acl.assert_called_once_with(d, sharing="app", owner=None)


@patch(_PATCH)
def test_list_app_filters_rows(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [
        _mock_dashboard("mine", app="search"),
        _mock_dashboard("alert_view", app="system"),
    ]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--json", "dashboards", "list", "--app", "search"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [d["app"] for d in data] == ["search"]


@patch(_PATCH)
def test_list_excludes_non_dashboards_by_default(mock_gc: MagicMock) -> None:
    view = _mock_dashboard("nav_thing")
    view.content = {**view.content, "isDashboard": "0"}
    mock_svc = MagicMock()
    mock_svc.dashboards.list.return_value = [_mock_dashboard("real"), view]
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list"])
    assert [d["name"] for d in json.loads(result.output)] == ["real"]

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list", "--all"])
    assert [d["name"] for d in json.loads(result.output)] == [
        "real",
        "nav_thing",
    ]
