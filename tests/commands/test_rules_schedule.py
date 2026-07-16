"""Tests for rules schedule subcommand and rules list --scheduled filter."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH_RULES = "splunkctl.commands.rules.get_client"
_PATCH_SCHED = "splunkctl.commands.rules_schedule.get_client"


def _mock_ss_scheduled(
    name: str, *, is_scheduled: str = "1", disabled: str = "0"
) -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": "index=main | stats count",
        "cron_schedule": "*/5 * * * *",
        "is_scheduled": is_scheduled,
        "disabled": disabled,
        "actions": "",
        "next_scheduled_time": "2025-06-01T00:05:00",
        "description": "",
        "dispatch.earliest_time": "-1h",
        "dispatch.latest_time": "now",
    }
    ss.access = {"app": "search", "owner": "admin"}
    return ss


def _setup_svc(mock_gc: MagicMock, items: list[MagicMock] | None = None) -> MagicMock:
    svc = MagicMock()
    if items is not None:
        svc.saved_searches.list.return_value = items
    mock_gc.return_value.service = svc
    return svc


# --- rules list --scheduled ---


@patch(_PATCH_RULES)
def test_list_scheduled_filter(mock_gc: MagicMock) -> None:
    """--scheduled filters to is_scheduled=1 only."""
    sched = _mock_ss_scheduled("sched-rule", is_scheduled="1")
    unsched = _mock_ss_scheduled("unsched-rule", is_scheduled="0")
    _setup_svc(mock_gc, [sched, unsched])

    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--scheduled"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    names = [r["name"] for r in rows]
    assert "sched-rule" in names
    assert "unsched-rule" not in names


@patch(_PATCH_RULES)
def test_list_scheduled_empty(mock_gc: MagicMock) -> None:
    """--scheduled with no scheduled searches returns empty list."""
    unsched = _mock_ss_scheduled("unsched-rule", is_scheduled="0")
    _setup_svc(mock_gc, [unsched])

    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--scheduled"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows == []


# --- rules schedule ---


@patch(_PATCH_SCHED)
def test_schedule_shows_scheduled_only(mock_gc: MagicMock) -> None:
    sched = _mock_ss_scheduled("cron-rule", is_scheduled="1")
    unsched = _mock_ss_scheduled("ad-hoc", is_scheduled="0")
    _setup_svc(mock_gc, [sched, unsched])

    result = CliRunner().invoke(cli, ["--json", "rules", "schedule"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    names = [r["name"] for r in rows]
    assert "cron-rule" in names
    assert "ad-hoc" not in names


@patch(_PATCH_SCHED)
def test_schedule_json_has_all_fields(mock_gc: MagicMock) -> None:
    ss = _mock_ss_scheduled("det-1")
    _setup_svc(mock_gc, [ss])

    result = CliRunner().invoke(cli, ["--json", "rules", "schedule"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "det-1"
    assert row["cron_schedule"] == "*/5 * * * *"
    assert row["next_scheduled_time"] == "2025-06-01T00:05:00"
    assert row["dispatch.earliest_time"] == "-1h"
    assert row["dispatch.latest_time"] == "now"
    assert row["is_scheduled"] == "1"
    assert row["disabled"] == "0"
    assert "qualifiedSearch" in row


@patch(_PATCH_SCHED)
def test_schedule_table_columns(mock_gc: MagicMock) -> None:
    ss = _mock_ss_scheduled("det-2")
    _setup_svc(mock_gc, [ss])

    result = CliRunner().invoke(cli, ["rules", "schedule"])
    assert result.exit_code == 0, result.output
    # Table output should contain the expected column headers.
    assert "name" in result.output
    assert "cron" in result.output
    assert "next_run" in result.output
    assert "window" in result.output
    assert "enabled" in result.output


@patch(_PATCH_SCHED)
def test_schedule_empty(mock_gc: MagicMock) -> None:
    unsched = _mock_ss_scheduled("ad-hoc", is_scheduled="0")
    _setup_svc(mock_gc, [unsched])

    result = CliRunner().invoke(cli, ["--json", "rules", "schedule"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows == []


@patch(_PATCH_SCHED)
def test_schedule_disabled_shows_no(mock_gc: MagicMock) -> None:
    ss = _mock_ss_scheduled("disabled-rule", disabled="1")
    _setup_svc(mock_gc, [ss])

    result = CliRunner().invoke(cli, ["--json", "rules", "schedule"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["disabled"] == "1"
