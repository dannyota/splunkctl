"""Tests for the es (Enterprise Security notable triage) commands."""

import json
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from splunkctl.commands.common import spl_quote
from splunkctl.commands.es import _list_spl, _status_to_int
from splunkctl.main import cli

_PATCH = "splunkctl.commands.es.get_client"
_READ_RESULTS = "splunkctl.commands.es.read_results"


def _mock_svc_with_es() -> MagicMock:
    """A service mock where the ES app entity fetch succeeds."""
    svc = MagicMock()
    svc.apps.__getitem__.return_value = MagicMock()
    return svc


def _mock_svc_without_es() -> MagicMock:
    """A service mock where the ES app entity fetch raises KeyError."""
    svc = MagicMock()
    svc.apps.__getitem__.side_effect = KeyError("no such app")
    return svc


def _http_error(status: int, reason: str, msg: str) -> Exception:
    """Build a real splunklib HTTPError, matching what a live call actually
    raises (so errors.classify's name-based check applies)."""
    from splunklib.binding import HTTPError

    xml_body = (
        f'<response><messages><msg type="ERROR">{msg}</msg></messages></response>'
    ).encode()
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    resp.body.read.return_value = xml_body
    resp.headers = []
    return HTTPError(resp)


# --- unit: status mapping ---


def test_status_to_int_maps_known_names() -> None:
    assert _status_to_int("new") == "1"
    assert _status_to_int("in progress") == "2"
    assert _status_to_int("closed") == "5"


def test_status_to_int_case_insensitive() -> None:
    assert _status_to_int("Closed") == "5"
    assert _status_to_int("UNASSIGNED") == "0"


def test_status_to_int_passes_digits_through() -> None:
    assert _status_to_int("3") == "3"
    assert _status_to_int("99") == "99"


def test_status_to_int_rejects_unknown() -> None:
    with pytest.raises(click.BadParameter):
        _status_to_int("bogus")


# --- unit: SPL quoting ---


def test_quoted_escapes_embedded_quotes() -> None:
    assert spl_quote('bob"smith') == '"bob\\"smith"'


def test_quoted_escapes_trailing_backslash() -> None:
    """Trailing backslash must be escaped to prevent SPL injection."""
    assert spl_quote("x\\") == '"x\\\\"'


def test_list_spl_owner_filter_with_trailing_backslash() -> None:
    """Owner filter with trailing backslash stays quoted (injection prevention)."""
    spl = _list_spl(status_filter=None, owner_filter="x\\", rule_filter=None)
    assert 'owner="x\\\\"' in spl
    # Verify it's still inside a quoted string, not breaking out to a pipe
    assert "| delete" not in spl


# --- unit: list SPL construction ---


def test_list_spl_base_only() -> None:
    spl = _list_spl(status_filter=None, owner_filter=None, rule_filter=None)
    assert spl.startswith("search index=notable ")
    assert "| sort - _time" in spl
    assert "| rename _time as time, rule_name as rule" in spl
    assert "table time, rule, security_domain, urgency, status, owner, event_id" in spl


def test_list_spl_composes_status_filter() -> None:
    spl = _list_spl(status_filter="new", owner_filter=None, rule_filter=None)
    assert "status=1" in spl


def test_list_spl_composes_owner_filter() -> None:
    spl = _list_spl(status_filter=None, owner_filter="analyst1", rule_filter=None)
    assert 'owner="analyst1"' in spl


def test_list_spl_composes_rule_filter() -> None:
    spl = _list_spl(status_filter=None, owner_filter=None, rule_filter="brute")
    assert 'rule_name="*brute*"' in spl


def test_list_spl_composes_all_filters() -> None:
    spl = _list_spl(status_filter="2", owner_filter="a b", rule_filter="beacon")
    assert "status=2" in spl
    assert 'owner="a b"' in spl
    assert 'rule_name="*beacon*"' in spl


# --- feature detection ---


@patch(_PATCH)
def test_notables_list_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(cli, ["--json", "es", "notables", "list"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"
    assert "SplunkEnterpriseSecuritySuite" in payload["error"]["message"]


@patch(_PATCH)
def test_notables_get_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(cli, ["--json", "es", "notables", "get", "abc123"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"


@patch(_PATCH)
def test_notables_update_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(
        cli,
        ["--yes", "--json", "es", "notables", "update", "abc123", "--status", "new"],
    )
    assert result.exit_code == 1
    # stderr also carries the guard's "Applying: ..." line ahead of the
    # envelope; the envelope itself is the last line.
    payload = json.loads(result.stderr.strip().splitlines()[-1])
    assert payload["error"]["kind"] == "not_found"


# --- notables list ---


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_notables_list_defaults(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc
    mock_read.return_value = [
        {
            "time": "2026-07-02T10:00:00",
            "rule": "Brute Force",
            "security_domain": "access",
            "urgency": "high",
            "status": "1",
            "owner": "unassigned",
            "event_id": "evt-1",
        }
    ]

    result = CliRunner().invoke(cli, ["--json", "es", "notables", "list"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows[0]["event_id"] == "evt-1"

    _, kwargs = svc.jobs.oneshot.call_args
    assert kwargs["earliest_time"] == "-24h"
    assert kwargs["latest_time"] == "now"
    assert kwargs["count"] == 100
    spl = svc.jobs.oneshot.call_args.args[0]
    assert spl.startswith("search index=notable")


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_notables_list_custom_filters_and_time(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc
    mock_read.return_value = []

    result = CliRunner().invoke(
        cli,
        [
            "es",
            "notables",
            "list",
            "--since",
            "-7d",
            "--until",
            "now",
            "--status",
            "new",
            "--owner",
            "analyst1",
            "--rule",
            "beacon",
            "--limit",
            "25",
        ],
    )
    assert result.exit_code == 0
    spl = svc.jobs.oneshot.call_args.args[0]
    kwargs = svc.jobs.oneshot.call_args.kwargs
    assert "status=1" in spl
    assert 'owner="analyst1"' in spl
    assert 'rule_name="*beacon*"' in spl
    assert kwargs["earliest_time"] == "-7d"
    assert kwargs["count"] == 25


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_notables_list_empty(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_with_es()
    mock_read.return_value = []

    # Piped default resolves to JSON: empty payload is "[]", not a message.
    result = CliRunner().invoke(cli, ["es", "notables", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"

    result = CliRunner().invoke(cli, ["--format", "table", "es", "notables", "list"])
    assert result.exit_code == 0
    assert "No notable events found" in result.stderr


# --- notables get ---


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_notables_get_full_fields(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc
    mock_read.return_value = [
        {
            "event_id": "evt-1",
            "rule_name": "Brute Force",
            "security_domain": "access",
            "urgency": "high",
            "status": "1",
            "owner": "unassigned",
            "extra_field": "value",
        }
    ]

    result = CliRunner().invoke(cli, ["--json", "es", "notables", "get", "evt-1"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert rows[0]["extra_field"] == "value"
    spl = svc.jobs.oneshot.call_args.args[0]
    assert 'event_id="evt-1"' in spl


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_notables_get_not_found(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_with_es()
    mock_read.return_value = []

    result = CliRunner().invoke(cli, ["--json", "es", "notables", "get", "nope"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"


# --- notables update ---


@patch(_PATCH)
def test_notables_update_dry_run_previews_ids_and_changes(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "es",
            "notables",
            "update",
            "evt-1",
            "evt-2",
            "--status",
            "closed",
            "--comment",
            "done",
        ],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "evt-1" in result.stderr
    assert "evt-2" in result.stderr
    assert "status=5" in result.stderr
    assert "comment=done" in result.stderr
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_notables_update_yes_posts_supplied_fields_only(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "es",
            "notables",
            "update",
            "evt-1",
            "--status",
            "new",
            "--owner",
            "analyst1",
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    args, kwargs = svc.post.call_args
    assert args[0] == "/services/notable_update"
    assert kwargs["ruleUIDs"] == ["evt-1"]
    assert kwargs["status"] == "1"
    assert kwargs["newOwner"] == "analyst1"
    assert "urgency" not in kwargs
    assert "disposition" not in kwargs
    assert "comment" not in kwargs


@patch(_PATCH)
def test_notables_update_bulk_ids_all_included(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "es",
            "notables",
            "update",
            "evt-1",
            "evt-2",
            "evt-3",
            "--urgency",
            "critical",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = svc.post.call_args
    assert kwargs["ruleUIDs"] == ["evt-1", "evt-2", "evt-3"]
    assert kwargs["urgency"] == "critical"


@patch(_PATCH)
def test_notables_update_disposition_passthrough(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "es",
            "notables",
            "update",
            "evt-1",
            "--disposition",
            "disposition:2",
        ],
    )
    assert result.exit_code == 0
    _, kwargs = svc.post.call_args
    assert kwargs["disposition"] == "disposition:2"


@patch(_PATCH)
def test_notables_update_no_fields_is_usage_error(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["--yes", "es", "notables", "update", "evt-1"])
    assert result.exit_code == 2
    mock_gc.assert_not_called()


def test_notables_update_missing_event_ids_is_usage_error() -> None:
    result = CliRunner().invoke(
        cli, ["--yes", "es", "notables", "update", "--status", "new"]
    )
    assert result.exit_code == 2


@patch(_PATCH)
def test_notables_update_permission_denied_classified_envelope(
    mock_gc: MagicMock,
) -> None:
    svc = _mock_svc_with_es()
    svc.post.side_effect = _http_error(
        403, "Forbidden", "You don't have permission to modify notables."
    )
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "--json",
            "es",
            "notables",
            "update",
            "evt-1",
            "--status",
            "closed",
        ],
    )
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "permission"
    assert payload["error"]["http_status"] == 403
    assert "Traceback" not in result.output
    assert "Traceback" not in result.stderr


# --- commands --json self-discovery ---


def test_commands_json_includes_es_group() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.output)
    names = [c["name"] for c in tree["commands"]]
    assert "es" in names
    es_node = next(c for c in tree["commands"] if c["name"] == "es")
    notables_node = next(c for c in es_node["subcommands"] if c["name"] == "notables")
    sub_names = [c["name"] for c in notables_node["subcommands"]]
    assert set(sub_names) == {"list", "get", "update"}
    update_node = next(c for c in notables_node["subcommands"] if c["name"] == "update")
    assert update_node.get("guarded") is True
