"""--app/--owner namespace scoping for ``rules list`` and ``rules get``.

When --app is given without --owner, both commands must wildcard the owner
(owner="-") so app-private saved searches owned by other users are still
found — matching the sibling dashboards/lookups commands.
"""

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


@patch(_PATCH)
def test_list_rules_default_namespace_unchanged(mock_gc: MagicMock) -> None:
    """No --app/--owner: call .list() exactly as before this feature."""
    svc = _setup_svc(mock_gc, [])
    result = CliRunner().invoke(cli, ["--json", "rules", "list"])
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with()


@patch(_PATCH)
def test_list_rules_with_owner_scopes_namespace(mock_gc: MagicMock) -> None:
    """--owner alone (no --app): unchanged, owner passed as-is."""
    svc = _setup_svc(mock_gc, [])
    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--owner", "admin"])
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with(owner="admin")


@patch(_PATCH)
def test_list_rules_with_app_scopes_across_owners(mock_gc: MagicMock) -> None:
    """--app without --owner: wildcard owner="-" like dashboards/lookups."""
    ss = _mock_ss("sse-rule")
    svc = _setup_svc(mock_gc, [ss])
    result = CliRunner().invoke(
        cli, ["--json", "rules", "list", "--app", "Splunk_Security_Essentials"]
    )
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with(
        app="Splunk_Security_Essentials", owner="-"
    )
    assert "sse-rule" in result.output


@patch(_PATCH)
def test_list_rules_with_app_and_owner_both_given(mock_gc: MagicMock) -> None:
    """--app and --owner both given: pass both as given, unchanged."""
    svc = _setup_svc(mock_gc, [])
    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "rules",
            "list",
            "--app",
            "Splunk_Security_Essentials",
            "--owner",
            "alice",
        ],
    )
    assert result.exit_code == 0
    svc.saved_searches.list.assert_called_once_with(
        app="Splunk_Security_Essentials", owner="alice"
    )


@patch(_PATCH)
def test_get_rule_with_app_resolves_across_owners(mock_gc: MagicMock) -> None:
    """--app without --owner: _resolve_rule wildcards owner="-" like rules list."""
    ss = _mock_ss("sse-rule")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.list.return_value = [ss]

    result = CliRunner().invoke(
        cli,
        ["--json", "rules", "get", "sse-rule", "--app", "Splunk_Security_Essentials"],
    )
    assert result.exit_code == 0, result.output
    svc.saved_searches.list.assert_called_once_with(
        search='name="sse-rule"',
        count=10,
        app="Splunk_Security_Essentials",
        owner="-",
    )
    assert "sse-rule" in result.output


@patch(_PATCH)
def test_get_rule_with_app_and_owner_both_given(mock_gc: MagicMock) -> None:
    """--app and --owner both given: pass both as given, unchanged."""
    ss = _mock_ss("sse-rule")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.list.return_value = [ss]

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "rules",
            "get",
            "sse-rule",
            "--app",
            "Splunk_Security_Essentials",
            "--owner",
            "alice",
        ],
    )
    assert result.exit_code == 0, result.output
    svc.saved_searches.list.assert_called_once_with(
        search='name="sse-rule"',
        count=10,
        app="Splunk_Security_Essentials",
        owner="alice",
    )


@patch(_PATCH)
def test_get_rule_with_owner_only_unchanged(mock_gc: MagicMock) -> None:
    """--owner alone (no --app): unchanged, owner passed as-is, no app key."""
    ss = _mock_ss("r1")
    svc = _setup_svc(mock_gc)
    svc.saved_searches.list.return_value = [ss]

    result = CliRunner().invoke(
        cli, ["--json", "rules", "get", "r1", "--owner", "alice"]
    )
    assert result.exit_code == 0, result.output
    svc.saved_searches.list.assert_called_once_with(
        search='name="r1"', count=10, owner="alice"
    )
