from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_ss(name: str = "test-rule") -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": "index=main | stats count",
        "cron_schedule": "*/5 * * * *",
        "is_scheduled": "1",
        "disabled": "0",
        "actions": "email",
        "next_scheduled_time": "2025-01-01T00:00:00",
        "description": "Test rule",
    }
    ss.access = {"app": "search", "owner": "admin"}
    return ss


def _setup_svc(mock_gc: MagicMock, items: list[MagicMock] | None = None) -> MagicMock:
    svc = MagicMock()
    if items is not None:
        svc.saved_searches.list.return_value = items
    mock_gc.return_value.service = svc
    return svc


@patch("splunkctl.commands.rules.get_client")
def test_list_rules(mock_gc: MagicMock) -> None:
    ss1, ss2 = _mock_ss("rule-1"), _mock_ss("rule-2")
    _setup_svc(mock_gc, [ss1, ss2])

    result = CliRunner().invoke(cli, ["--json", "rules", "list"])
    assert result.exit_code == 0
    assert "rule-1" in result.output
    assert "rule-2" in result.output


@patch("splunkctl.commands.rules.get_client")
def test_get_rule(mock_gc: MagicMock) -> None:
    ss = _mock_ss("my-rule")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["--json", "rules", "get", "my-rule"])
    assert result.exit_code == 0
    assert "my-rule" in result.output
    assert "index=main" in result.output


@patch("splunkctl.commands.rules.get_client")
def test_get_not_found(mock_gc: MagicMock) -> None:
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(cli, ["rules", "get", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


@patch("splunkctl.commands.rules.get_client")
def test_create_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        ["rules", "create", "--name", "r1", "--search", "index=main"],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.rules.get_client")
def test_create_applies(mock_gc: MagicMock) -> None:
    svc = _setup_svc(mock_gc)

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
        ],
    )
    assert result.exit_code == 0
    svc.saved_searches.create.assert_called_once_with("r1", search="index=main")


@patch("splunkctl.commands.rules.get_client")
def test_create_with_options(mock_gc: MagicMock) -> None:
    svc = _setup_svc(mock_gc)

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--cron",
            "*/5 * * * *",
            "--actions",
            "email",
            "--description",
            "test",
        ],
    )
    assert result.exit_code == 0
    svc.saved_searches.create.assert_called_once_with(
        "r1",
        search="index=main",
        cron_schedule="*/5 * * * *",
        is_scheduled="1",
        description="test",
        actions="email",
    )


@patch("splunkctl.commands.rules.get_client")
def test_update_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        ["rules", "update", "r1", "--search", "index=web"],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.rules.get_client")
def test_update_applies(mock_gc: MagicMock) -> None:
    ss = _mock_ss("r1")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(
        cli,
        ["--yes", "rules", "update", "r1", "--search", "index=web"],
    )
    assert result.exit_code == 0
    ss.update.assert_called_once_with(search="index=web")


@patch("splunkctl.commands.rules.get_client")
def test_update_no_changes(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["rules", "update", "r1"])
    assert result.exit_code == 1
    assert "No changes" in result.output


@patch("splunkctl.commands.rules.get_client")
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["rules", "delete", "r1"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.rules.get_client")
def test_delete_applies(mock_gc: MagicMock) -> None:
    ss = _mock_ss("r1")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["--yes", "rules", "delete", "r1"])
    assert result.exit_code == 0
    ss.delete.assert_called_once()


@patch("splunkctl.commands.rules.get_client")
def test_enable_applies(mock_gc: MagicMock) -> None:
    ss = _mock_ss("r1")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["--yes", "rules", "enable", "r1"])
    assert result.exit_code == 0
    ss.update.assert_called_once_with(disabled="0", is_scheduled="1")


@patch("splunkctl.commands.rules.get_client")
def test_disable_applies(mock_gc: MagicMock) -> None:
    ss = _mock_ss("r1")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["--yes", "rules", "disable", "r1"])
    assert result.exit_code == 0
    ss.update.assert_called_once_with(disabled="1")


@patch("splunkctl.commands.rules.get_client")
def test_history(mock_gc: MagicMock) -> None:
    ss = _mock_ss("r1")
    job = MagicMock()
    job.sid = "1234567890.42"
    job.content = {
        "dispatchState": "DONE",
        "runDuration": "1.23",
        "eventCount": "100",
        "resultCount": "50",
    }
    ss.history.return_value = [job]
    svc = _setup_svc(mock_gc)
    svc.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["--json", "rules", "history", "r1"])
    assert result.exit_code == 0
    assert "1234567890.42" in result.output
    assert "DONE" in result.output
