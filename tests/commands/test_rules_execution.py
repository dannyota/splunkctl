"""Scheduling and test-run regressions for saved searches."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules.get_client"


def _rule_client(mock_gc: MagicMock, *, cron: str = "") -> tuple[MagicMock, MagicMock]:
    service = mock_gc.return_value.service
    rule = service.saved_searches.__getitem__.return_value
    rule.content = {
        "search": "index=main | stats count",
        "disabled": "0",
        "cron_schedule": cron,
        "dispatch.earliest_time": "-2h",
        "dispatch.latest_time": "-5m",
    }
    rule.access = {"app": "security", "owner": "analyst"}
    return service, rule


def _assert_no_cron_advisory(stderr: str) -> None:
    lines = [
        line for line in stderr.splitlines() if "enabled but not scheduled" in line
    ]
    assert len(lines) == 1
    assert "no cron" in lines[0]


@pytest.mark.parametrize("cron", [None, "", "   ", "*/5 * * * *"])
@patch(_PATCH)
def test_create_explicitly_enables_and_schedules_only_with_cron(
    mock_gc: MagicMock, cron: str | None
) -> None:
    args = ["--yes", "rules", "create", "--name", "r1", "--search", "index=main"]
    if cron is not None:
        args += ["--cron", cron]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    kwargs = mock_gc.return_value.service.saved_searches.create.call_args.kwargs
    assert kwargs["disabled"] == "0"
    assert kwargs["is_scheduled"] == ("1" if cron and cron.strip() else "0")
    if not cron or not cron.strip():
        _assert_no_cron_advisory(result.stderr)
    else:
        assert "enabled but not scheduled" not in result.stderr


@pytest.mark.parametrize("cron", ["", "   ", "*/5 * * * *"])
@patch(_PATCH)
def test_enable_only_schedules_with_existing_cron(
    mock_gc: MagicMock, cron: str
) -> None:
    _, rule = _rule_client(mock_gc, cron=cron)
    result = CliRunner().invoke(cli, ["--yes", "rules", "enable", "r1"])
    assert result.exit_code == 0, result.output
    rule.update.assert_called_once_with(
        disabled="0", is_scheduled="1" if cron.strip() else "0"
    )
    if not cron.strip():
        _assert_no_cron_advisory(result.stderr)


@pytest.mark.parametrize(
    ("existing_cron", "new_cron", "scheduled"),
    [
        ("", None, "0"),
        ("*/5 * * * *", None, "1"),
        ("", "*/10 * * * *", "1"),
        ("*/5 * * * *", "", "0"),
    ],
)
@patch(_PATCH)
def test_update_enabled_uses_effective_cron(
    mock_gc: MagicMock, existing_cron: str, new_cron: str | None, scheduled: str
) -> None:
    _, rule = _rule_client(mock_gc, cron=existing_cron)
    args = ["--yes", "rules", "update", "r1", "--enabled"]
    if new_cron is not None:
        args += ["--cron", new_cron]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    kwargs = rule.update.call_args.kwargs
    assert kwargs["disabled"] == "0"
    assert kwargs["is_scheduled"] == scheduled
    if scheduled == "0":
        _assert_no_cron_advisory(result.stderr)


@patch(_PATCH)
def test_update_cron_activates_schedule(mock_gc: MagicMock) -> None:
    _, rule = _rule_client(mock_gc)
    result = CliRunner().invoke(
        cli, ["--yes", "rules", "update", "r1", "--cron", "*/10 * * * *"]
    )
    assert result.exit_code == 0, result.output
    rule.update.assert_called_once_with(cron_schedule="*/10 * * * *", is_scheduled="1")


@pytest.mark.parametrize("overrides", [False, True])
@pytest.mark.parametrize("disabled", ["1", True, "true"])
@patch(_PATCH)
def test_disabled_rule_runs_spl_in_app_with_same_window(
    mock_gc: MagicMock, overrides: bool, disabled: str | bool
) -> None:
    service, rule = _rule_client(mock_gc)
    rule.content["disabled"] = disabled
    job = service.jobs.create.return_value
    job.is_done.return_value = True
    job.results.return_value = io.BytesIO(b'{"results":[{"count":"3"}]}')
    rule.dispatch.return_value.is_done.return_value = True
    rule.dispatch.return_value.results.return_value = io.BytesIO(b'{"results":[]}')
    args = ["--json", "rules", "test", "r1", "--limit", "7"]
    if overrides:
        args += ["--earliest", "-7d", "--latest", "now"]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    rule.dispatch.assert_not_called()
    service.jobs.create.assert_called_once_with(
        "search index=main | stats count",
        app="security",
        exec_mode="normal",
        earliest_time="-7d" if overrides else "-2h",
        latest_time="now" if overrides else "-5m",
    )
    assert "disabled" in result.stderr.lower()
    assert "ad hoc" in result.stderr.lower()
    assert json.loads(result.stdout) == [{"count": "3"}]
    job.results.assert_called_once_with(output_mode="json", count=7)
    rule.update.assert_not_called()


@patch(_PATCH)
def test_enabled_rule_keeps_saved_search_dispatch_without_actions(
    mock_gc: MagicMock,
) -> None:
    service, rule = _rule_client(mock_gc)
    job = rule.dispatch.return_value
    job.is_done.return_value = True
    job.results.return_value = io.BytesIO(b'{"results":[]}')
    result = CliRunner().invoke(
        cli, ["--json", "rules", "test", "r1", "--earliest", "-7d", "--latest", "now"]
    )
    assert result.exit_code == 0, result.output
    rule.dispatch.assert_called_once_with(
        trigger_actions="0",
        **{"dispatch.earliest_time": "-7d", "dispatch.latest_time": "now"},
    )
    service.jobs.create.assert_not_called()
