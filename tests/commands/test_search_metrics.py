"""Tests for the search metrics subcommand."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.search.get_client"
_READER = "splunklib.results.JSONResultsReader"


@patch(_READER)
@patch(_PATCH)
def test_metrics_list_names(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [
        {"values(metric_name)": ["cpu.idle", "cpu.user", "mem.free"]}
    ]

    result = CliRunner().invoke(
        cli, ["--json", "search", "metrics", "--index", "my_metrics"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 3
    assert data[0] == {"metric_name": "cpu.idle"}
    assert data[2] == {"metric_name": "mem.free"}

    spl = mock_svc.jobs.oneshot.call_args.args[0]
    assert "mcatalog" in spl
    assert "values(metric_name)" in spl
    assert '"my_metrics"' in spl


@patch(_READER)
@patch(_PATCH)
def test_metrics_list_names_with_filter(
    mock_gc: MagicMock, mock_reader: MagicMock
) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [
        {"values(metric_name)": ["cpu.idle", "cpu.user", "mem.free"]}
    ]

    result = CliRunner().invoke(
        cli, ["--json", "search", "metrics", "--index", "m", "--filter", "cpu"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 2
    assert all(r["metric_name"].startswith("cpu") for r in data)


@patch(_READER)
@patch(_PATCH)
def test_metrics_dimensions(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"values(_dims)": ["host", "region", "datacenter"]}]

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "search",
            "metrics",
            "--index",
            "my_metrics",
            "--metric",
            "cpu.idle",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 3
    assert data[0] == {"dimension": "host"}
    assert data[1] == {"dimension": "region"}

    spl = mock_svc.jobs.oneshot.call_args.args[0]
    assert "values(_dims)" in spl
    assert '"cpu.idle"' in spl
    assert '"my_metrics"' in spl


@patch(_READER)
@patch(_PATCH)
def test_metrics_empty_result(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc
    mock_reader.return_value = []

    result = CliRunner().invoke(
        cli, ["--json", "search", "metrics", "--index", "empty_idx"]
    )
    assert result.exit_code == 0
    # empty JSON output (no metrics found)
    assert "No metrics found" in result.output or "[]" in result.output


@patch(_READER)
@patch(_PATCH)
def test_metrics_spl_quoting(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    """Values with special chars are safely quoted in SPL."""
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc
    mock_reader.return_value = []

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "search",
            "metrics",
            "--index",
            'idx"inject',
            "--metric",
            'met"ric',
        ],
    )
    assert result.exit_code == 0
    spl = mock_svc.jobs.oneshot.call_args.args[0]
    # Quotes should be escaped
    assert r"idx\"inject" in spl
    assert r"met\"ric" in spl
