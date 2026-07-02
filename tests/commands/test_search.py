import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.commands.search import _normalize_spl
from splunkctl.main import cli

_PATCH = "splunkctl.commands.search.get_client"
_READER = "splunkctl.commands.search.JSONResultsReader"


def test_normalize_spl_prepends_search() -> None:
    assert _normalize_spl("index=main") == "search index=main"


def test_normalize_spl_pipe_unchanged() -> None:
    assert _normalize_spl("| stats count") == "| stats count"


def test_normalize_spl_search_prefix_unchanged() -> None:
    assert _normalize_spl("search index=main") == "search index=main"


def test_normalize_spl_strips_whitespace() -> None:
    assert _normalize_spl("  index=main  ") == "search index=main"


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_run_search(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.is_done.return_value = True
    mock_job.results.return_value = "stream"

    mock_svc = MagicMock()
    mock_svc.jobs.create.return_value = mock_job
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"host": "srv1", "source": "syslog"}]

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "run", "index=main"])
    assert result.exit_code == 0
    assert "srv1" in result.output
    mock_svc.jobs.create.assert_called_once()
    assert mock_svc.jobs.create.call_args.args[0] == "search index=main"


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_run_search_with_time_range(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.is_done.return_value = True
    mock_job.results.return_value = "stream"

    mock_svc = MagicMock()
    mock_svc.jobs.create.return_value = mock_job
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"count": "42"}]

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "search",
            "run",
            "--earliest",
            "-24h",
            "--latest",
            "now",
            "index=main",
        ],
    )
    assert result.exit_code == 0
    kw = mock_svc.jobs.create.call_args.kwargs
    assert kw["earliest_time"] == "-24h"
    assert kw["latest_time"] == "now"


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_run_search_pipe_query(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.is_done.return_value = True
    mock_job.results.return_value = "stream"

    mock_svc = MagicMock()
    mock_svc.jobs.create.return_value = mock_job
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"count": "10"}]

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "run", "| stats count"])
    assert result.exit_code == 0
    assert mock_svc.jobs.create.call_args.args[0] == "| stats count"


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_export_search(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.export.return_value = "stream"
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"host": "srv2"}]

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "export", "index=main"])
    assert result.exit_code == 0
    assert "srv2" in result.output
    mock_svc.jobs.export.assert_called_once()


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_oneshot_search(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.oneshot.return_value = "stream"
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"host": "srv3"}]

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "oneshot", "index=main"])
    assert result.exit_code == 0
    assert "srv3" in result.output
    mock_svc.jobs.oneshot.assert_called_once()
    kw = mock_svc.jobs.oneshot.call_args.kwargs
    assert kw["count"] == 100


@patch("splunkctl.commands.search.get_client")
def test_list_jobs(mock_gc: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "1234567890.1"
    mock_job.content = {
        "dispatchState": "DONE",
        "earliestTime": "-24h",
        "latestTime": "now",
        "eventCount": "100",
        "runDuration": "1.5",
    }

    mock_svc = MagicMock()
    mock_svc.jobs.__iter__ = MagicMock(return_value=iter([mock_job]))
    mock_gc.return_value.service = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "jobs"])
    assert result.exit_code == 0
    assert "1234567890.1" in result.output
    assert "DONE" in result.output


@patch("splunkctl.commands.search.JSONResultsReader")
@patch("splunkctl.commands.search.get_client")
def test_get_job_done(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "1234567890.2"
    mock_job.content = {
        "dispatchState": "DONE",
        "earliestTime": "-24h",
        "latestTime": "now",
        "eventCount": "50",
        "resultCount": "50",
        "runDuration": "2.0",
    }
    mock_job.is_done.return_value = True
    mock_job.results.return_value = "stream"

    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"host": "srv4", "_raw": "event data"}]

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "job", "1234567890.2"])
    assert result.exit_code == 0
    assert "srv4" in result.output


@patch("splunkctl.commands.search.get_client")
def test_get_job_running(mock_gc: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "1234567890.3"
    mock_job.content = {
        "dispatchState": "RUNNING",
        "earliestTime": "-24h",
        "latestTime": "now",
        "eventCount": "0",
        "resultCount": "0",
        "runDuration": "0.5",
    }
    mock_job.is_done.return_value = False

    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "search", "job", "1234567890.3"])
    assert result.exit_code == 0
    assert "RUNNING" in result.output


@patch("splunkctl.commands.search.get_client")
def test_get_job_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(side_effect=KeyError("nosuchsid"))
    mock_gc.return_value.service = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "job", "nosuchsid"])
    assert result.exit_code != 0


@patch("splunkctl.commands.search.get_client")
def test_cancel_dry_run(mock_gc: MagicMock) -> None:
    mock_job = MagicMock()
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "cancel", "test_sid"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_job.cancel.assert_not_called()


@patch("splunkctl.commands.search.get_client")
def test_cancel_with_yes(mock_gc: MagicMock) -> None:
    mock_job = MagicMock()
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc

    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "search", "cancel", "test_sid"])
    assert result.exit_code == 0
    mock_job.cancel.assert_called_once()


@patch("splunkctl.commands.search.get_client")
def test_upload_dry_run(mock_gc: MagicMock, tmp_path: MagicMock) -> None:
    f = tmp_path / "threats.csv"
    f.write_text("ip,score\n1.2.3.4,100\n")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["search", "upload", "--path", str(f), "--index", "main"],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output
    mock_gc.return_value.service.post.assert_not_called()


@patch("splunkctl.commands.search.get_client")
def test_upload_confirmed(mock_gc: MagicMock, tmp_path: MagicMock) -> None:
    f = tmp_path / "access.log"
    f.write_text("GET /index.html 200\n")
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "search",
            "upload",
            "--path",
            str(f),
            "--index",
            "main",
            "--sourcetype",
            "access_combined",
        ],
    )
    assert result.exit_code == 0
    assert "Uploaded" in result.output
    mock_svc.post.assert_called_once()
    call_kwargs = mock_svc.post.call_args
    assert call_kwargs[1]["index"] == "main"
    assert call_kwargs[1]["sourcetype"] == "access_combined"


@patch("splunkctl.commands.search.get_client")
def test_upload_default_source(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    f = tmp_path / "firewall.log"
    f.write_text("deny 10.0.0.1\n")
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "search", "upload", "--path", str(f)],
    )
    assert result.exit_code == 0
    call_kw = mock_svc.post.call_args
    assert call_kw[1]["source"] == "firewall.log"


@patch(_READER)
@patch(_PATCH)
def test_run_detach_renders_sid_no_poll(
    mock_gc: MagicMock, mock_reader: MagicMock
) -> None:
    mock_job = MagicMock()
    mock_job.sid = "999.1"
    mock_svc = MagicMock()
    mock_svc.jobs.create.return_value = mock_job
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--json", "search", "run", "--detach", "index=main"]
    )
    assert result.exit_code == 0
    assert '"999.1"' in result.output
    assert '"running"' in result.output
    mock_job.is_done.assert_not_called()


@patch(_READER)
@patch(_PATCH)
def test_run_truncation_warning(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "888.1"
    mock_job.is_done.return_value = True
    mock_job.results.return_value = "stream"
    mock_job.content = {"resultCount": "5000"}
    mock_svc = MagicMock()
    mock_svc.jobs.create.return_value = mock_job
    mock_gc.return_value.service = mock_svc

    mock_reader.return_value = [{"a": "1"}]

    result = CliRunner().invoke(
        cli, ["--json", "search", "run", "--limit", "1", "index=main"]
    )
    assert result.exit_code == 0
    assert "Showing 1 of 5000" in result.stderr
    assert "888.1" in result.stderr


@patch(_READER)
@patch(_PATCH)
def test_job_paging_kwargs(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "777.1"
    mock_job.is_done.return_value = True
    mock_job.content = {
        "dispatchState": "DONE",
        "resultCount": "100",
        "eventCount": "100",
    }
    mock_job.results.return_value = "stream"
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc
    mock_reader.return_value = [{"x": "1"}]

    result = CliRunner().invoke(
        cli,
        ["--json", "search", "job", "777.1", "--offset", "10", "--count", "5"],
    )
    assert result.exit_code == 0
    kw = mock_job.results.call_args.kwargs
    assert kw["offset"] == 10
    assert kw["count"] == 5


@patch(_READER)
@patch(_PATCH)
def test_job_events_flag(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "666.1"
    mock_job.is_done.return_value = True
    mock_job.content = {"dispatchState": "DONE", "resultCount": "10"}
    mock_job.events.return_value = "estream"
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc
    mock_reader.return_value = [{"_raw": "evt"}]

    result = CliRunner().invoke(cli, ["--json", "search", "job", "666.1", "--events"])
    assert result.exit_code == 0
    mock_job.events.assert_called_once()
    mock_job.results.assert_not_called()


@patch(_READER)
@patch(_PATCH)
def test_job_status_only(mock_gc: MagicMock, mock_reader: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "555.1"
    mock_job.is_done.return_value = True
    mock_job.content = {
        "dispatchState": "DONE",
        "resultCount": "50",
        "eventCount": "50",
    }
    mock_svc = MagicMock()
    mock_svc.jobs.__getitem__ = MagicMock(return_value=mock_job)
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--json", "search", "job", "555.1", "--status-only"]
    )
    assert result.exit_code == 0
    assert '"DONE"' in result.output
    assert "is_done" in result.output
    mock_job.results.assert_not_called()


@patch(_PATCH)
def test_jobs_includes_owner_and_spl(mock_gc: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.sid = "444.1"
    mock_job.content = {
        "dispatchState": "DONE",
        "author": "admin",
        "search": "search index=main | stats count",
        "eventCount": "10",
        "runDuration": "0.5",
    }
    mock_svc = MagicMock()
    mock_svc.jobs.__iter__ = MagicMock(return_value=iter([mock_job]))
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "search", "jobs"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["owner"] == "admin"
    assert "stats count" in data[0]["spl"]
