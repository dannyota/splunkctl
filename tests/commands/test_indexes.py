"""Tests for index management commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.indexes.get_client"


def _mock_index(
    name: str = "main",
    datatype: str = "event",
    total: int = 1000,
    size: int = 50,
) -> MagicMock:
    idx = MagicMock()
    idx.name = name
    idx.content = {
        "datatype": datatype,
        "totalEventCount": total,
        "currentDBSizeMB": size,
        "maxTotalDataSizeMB": 500000,
        "maxDataSize": "auto_high_volume",
        "homePath_expanded": f"/opt/splunk/var/lib/splunk/{name}/db",
        "coldPath_expanded": f"/opt/splunk/var/lib/splunk/{name}/colddb",
        "frozenTimePeriodInSecs": 188697600,
        "maxHotBuckets": 10,
        "maxWarmDBCount": 300,
        "minTime": "2024-01-01T00:00:00+0000",
        "maxTime": "2026-06-29T00:00:00+0000",
        "repFactor": "0",
        "disabled": False,
        "isInternal": False,
    }
    return idx


@patch(_PATCH)
def test_list_indexes(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.list.return_value = [
        _mock_index("main"),
        _mock_index("_internal", total=500, size=20),
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "indexes", "list"])
    assert result.exit_code == 0
    assert "main" in result.output
    assert "_internal" in result.output


@patch(_PATCH)
def test_get_index(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.__getitem__.return_value = _mock_index()
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "indexes", "get", "main"])
    assert result.exit_code == 0
    assert "main" in result.output
    assert "homePath_expanded" in result.output
    assert "maxHotBuckets" in result.output


@patch(_PATCH)
def test_get_index_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["indexes", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch(_PATCH)
def test_create_index_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["indexes", "create", "--name", "test_idx", "--datatype", "event"]
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.return_value.service.indexes.create.assert_not_called()


@patch(_PATCH)
def test_create_index_confirmed(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "indexes", "create", "--name", "test_idx", "--max-size", "100"],
    )
    assert result.exit_code == 0
    mock_gc.return_value.service.indexes.create.assert_called_once_with(
        "test_idx", maxDataSizeMB=100
    )


@patch(_PATCH)
def test_create_index_all_options(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "indexes",
            "create",
            "--name",
            "myidx",
            "--datatype",
            "metric",
            "--max-size",
            "200",
            "--frozen-period",
            "86400",
            "--home-path",
            "/data/hot",
            "--cold-path",
            "/data/cold",
        ],
    )
    assert result.exit_code == 0
    mock_gc.return_value.service.indexes.create.assert_called_once_with(
        "myidx",
        datatype="metric",
        maxDataSizeMB=200,
        frozenTimePeriodInSecs=86400,
        homePath="/data/hot",
        coldPath="/data/cold",
    )


@patch(_PATCH)
def test_update_index_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["indexes", "update", "main", "--max-size", "1000"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_update_index_confirmed(mock_gc: MagicMock) -> None:
    idx = _mock_index()
    mock_gc.return_value.service.indexes.__getitem__.return_value = idx
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "indexes", "update", "main", "--frozen-period", "86400"],
    )
    assert result.exit_code == 0
    idx.update.assert_called_once_with(frozenTimePeriodInSecs=86400)


@patch(_PATCH)
def test_update_index_no_options(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "update", "main"])
    assert result.exit_code != 0
    assert "No settings" in result.output


@patch(_PATCH)
def test_update_index_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--yes", "indexes", "update", "nope", "--max-size", "100"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output


@patch(_PATCH)
def test_delete_index_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["indexes", "delete", "test_idx"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_delete_index_confirmed(mock_gc: MagicMock) -> None:
    idx = _mock_index("test_idx")
    mock_gc.return_value.service.indexes.__getitem__.return_value = idx
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "delete", "test_idx"])
    assert result.exit_code == 0
    idx.delete.assert_called_once()


@patch(_PATCH)
def test_delete_index_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "delete", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch(_PATCH)
def test_clean_index_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["indexes", "clean", "main"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_clean_index_confirmed(mock_gc: MagicMock) -> None:
    idx = _mock_index()
    mock_gc.return_value.service.indexes.__getitem__.return_value = idx
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "clean", "main"])
    assert result.exit_code == 0
    idx.clean.assert_called_once_with(timeout=60)


@patch(_PATCH)
def test_clean_index_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.indexes.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "clean", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch(_PATCH)
def test_reload_indexes_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["indexes", "reload"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_reload_indexes_confirmed(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "indexes", "reload"])
    assert result.exit_code == 0
    mock_gc.return_value.service.post.assert_called_once_with(
        "/services/data/indexes/_reload"
    )
