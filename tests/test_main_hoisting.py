"""Global flag hoisting — flags work in any position without shadowing leaf options."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_index(name: str = "main") -> MagicMock:
    idx = MagicMock()
    idx.name = name
    idx.content = {"datatype": "event", "totalEventCount": 5}
    return idx


@patch("splunkctl.commands.indexes.get_client")
def test_out_after_subcommand_writes_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    mock_gc.return_value.service.indexes.list.return_value = [_mock_index()]
    out = tmp_path / "idx.json"
    result = CliRunner().invoke(cli, ["indexes", "list", "--json", "--out", str(out)])
    assert result.exit_code == 0
    assert json.loads(out.read_text())[0]["name"] == "main"


@patch("splunkctl.commands.dashboards.get_client")
def test_dashboards_export_local_out_untouched(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    d = MagicMock()
    d.name = "dash"
    d.export.return_value = "<dashboard/>"
    mock_gc.return_value.service.dashboards.list.return_value = [d]
    out = tmp_path / "dash.xml"
    result = CliRunner().invoke(
        cli, ["dashboards", "export", "dash", "--out", str(out)]
    )
    assert result.exit_code == 0
    assert out.read_text() == "<dashboard/>"


@patch("splunkctl.commands.indexes.get_client")
def test_leaf_option_shadowing_global_stays_local(mock_gc: MagicMock) -> None:
    idx = _mock_index("t")
    mock_gc.return_value.service.indexes.__getitem__.return_value = idx
    result = CliRunner().invoke(
        cli, ["--yes", "indexes", "clean", "t", "--clean-timeout", "90"]
    )
    assert result.exit_code == 0
    idx.clean.assert_called_once_with(timeout=90)


@patch("splunkctl.commands.indexes.get_client")
def test_trailing_json_still_hoists(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.list.return_value = [_mock_index()]
    result = CliRunner().invoke(cli, ["indexes", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["name"] == "main"
