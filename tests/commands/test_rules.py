import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules.get_client"


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


@patch(_PATCH)
def test_create_threshold_flags(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "det1",
            "--search",
            "index=_internal | head 1",
            "--cron",
            "*/5 * * * *",
            "--alert-comparator",
            "greater than",
            "--alert-threshold",
            "5",
            "--severity",
            "4",
            "--track",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = mock_gc.return_value.service.saved_searches.create.call_args
    assert kwargs["alert_type"] == "number of events"
    assert kwargs["alert_comparator"] == "greater than"
    assert kwargs["alert_threshold"] == "5"
    assert kwargs["alert.severity"] == "4"
    assert kwargs["alert.track"] == "1"
    assert kwargs["cron_schedule"] == "*/5 * * * *"


@patch(_PATCH)
def test_create_throttle_expands(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "det2",
            "--search",
            "x",
            "--throttle",
            "600",
            "--throttle-fields",
            "user,src",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = mock_gc.return_value.service.saved_searches.create.call_args
    assert kwargs["alert.suppress"] == "1"
    assert kwargs["alert.suppress.period"] == "600s"
    assert kwargs["alert.suppress.fields"] == "user,src"


@patch(_PATCH)
def test_create_set_passthrough_flags_win(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "det3",
            "--search",
            "x",
            "--set",
            "action.email.to=soc@example.com",
            "--set",
            "alert_threshold=99",
            "--alert-comparator",
            "greater than",
            "--alert-threshold",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = mock_gc.return_value.service.saved_searches.create.call_args
    assert kwargs["action.email.to"] == "soc@example.com"
    assert kwargs["alert_threshold"] == "5"


def test_create_comparator_requires_threshold() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "d",
            "--search",
            "x",
            "--alert-comparator",
            "greater than",
        ],
    )
    assert result.exit_code != 0
    assert "together" in result.output + result.stderr


@patch(_PATCH)
def test_update_alert_flags_and_app(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    ss.name = "det4"
    mock_gc.return_value.service.saved_searches.list.return_value = [ss]
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "update",
            "det4",
            "--app",
            "secops",
            "--earliest",
            "-24h",
            "--latest",
            "now",
            "--set",
            "alert.digest_mode=0",
        ],
    )
    assert result.exit_code == 0, result.output
    _, list_kwargs = mock_gc.return_value.service.saved_searches.list.call_args
    assert list_kwargs.get("app") == "secops"
    _, kwargs = ss.update.call_args
    assert kwargs["dispatch.earliest_time"] == "-24h"
    assert kwargs["dispatch.latest_time"] == "now"
    assert kwargs["alert.digest_mode"] == "0"


@patch(_PATCH)
def test_list_filter_narrows(mock_gc: MagicMock) -> None:
    a, b = MagicMock(), MagicMock()
    a.name = "zz_failed_logins"
    b.name = "Errors in the last day"
    for m in (a, b):
        m.content = {}
        m.access = {"app": "search"}
    mock_gc.return_value.service.saved_searches.list.return_value = [a, b]
    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--filter", "FAILED"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [r["name"] for r in rows] == ["zz_failed_logins"]


@patch(_PATCH)
def test_list_rules_default_namespace_unchanged(mock_gc: MagicMock) -> None:
    """No --app/--owner: call .list() exactly as before this feature."""
    svc = _setup_svc(mock_gc, [])
    result = CliRunner().invoke(cli, ["--json", "rules", "list"])
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with()


@patch(_PATCH)
def test_list_rules_with_app_scopes_namespace(mock_gc: MagicMock) -> None:
    ss = _mock_ss("sse-rule")
    svc = _setup_svc(mock_gc, [ss])
    result = CliRunner().invoke(
        cli, ["--json", "rules", "list", "--app", "Splunk_Security_Essentials"]
    )
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with(app="Splunk_Security_Essentials")
    assert "sse-rule" in result.output


@patch(_PATCH)
def test_list_rules_with_owner_scopes_namespace(mock_gc: MagicMock) -> None:
    svc = _setup_svc(mock_gc, [])
    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--owner", "admin"])
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with(owner="admin")


@patch(_PATCH)
def test_get_shows_acl(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    ss.name = "r1"
    ss.content = {"search": "x", "alert_comparator": "greater than"}
    ss.access = {"app": "secops", "owner": "alice", "sharing": "app"}
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss
    result = CliRunner().invoke(cli, ["--json", "rules", "get", "r1"])
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row["app"] == "secops"
    assert row["owner"] == "alice"
    assert row["sharing"] == "app"
    assert row["alert_comparator"] == "greater than"


@patch(_PATCH)
def test_get_rule_with_app_resolves_app_private_rule(mock_gc: MagicMock) -> None:
    ss = _mock_ss("sse-rule")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.list.return_value = [ss]

    result = CliRunner().invoke(
        cli,
        ["--json", "rules", "get", "sse-rule", "--app", "Splunk_Security_Essentials"],
    )
    assert result.exit_code == 0, result.output
    svc.saved_searches.list.assert_called_once_with(
        search='name="sse-rule"', count=10, app="Splunk_Security_Essentials"
    )
    assert "sse-rule" in result.output


@patch(_PATCH)
def test_share_posts_acl(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    ss.access = {"sharing": "user", "owner": "splunk"}
    mock_client = mock_gc.return_value
    mock_client.service.saved_searches.__getitem__.return_value = ss
    result = CliRunner().invoke(
        cli, ["--yes", "rules", "share", "r1", "--sharing", "app"]
    )
    assert result.exit_code == 0, result.output
    mock_client.set_acl.assert_called_once_with(ss, sharing="app", owner=None)


@patch(_PATCH)
def test_rules_test_dispatches_with_window(mock_gc: MagicMock) -> None:
    job = MagicMock()
    job.is_done.return_value = True
    job.results.return_value = MagicMock()
    ss = MagicMock()
    ss.dispatch.return_value = job
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    with patch("splunkctl.commands.rules.read_results", return_value=[{"count": "3"}]):
        result = CliRunner().invoke(
            cli, ["--json", "rules", "test", "r1", "--earliest", "-24h"]
        )
    assert result.exit_code == 0, result.output
    _, kwargs = ss.dispatch.call_args
    assert kwargs["dispatch.earliest_time"] == "-24h"
    assert kwargs["trigger_actions"] == "0"
    assert json.loads(result.stdout)[0]["count"] == "3"
