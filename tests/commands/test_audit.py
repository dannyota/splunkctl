"""Tests for the audit (change audit + RBAC attestation) commands."""

import csv
import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.audit.get_client"
_READ_RESULTS = "splunkctl.commands.audit.read_results"

_LEGACY_NO_OBJECT = (
    "Audit:[timestamp=07-02-2026 19:34:53.689, user=analyst1, "
    "action=list_all_objects, info=granted , cap=1]"
)
_LEGACY_WITH_OBJECT = (
    "Audit:[timestamp=07-02-2026 19:15:29.443, user=analyst2, "
    'action=edit_user, info=granted object="jdoe" operation=list, cap=1]'
)
_JSON_OBJECT_EDIT = (
    '{"timestamp":"07-02-2026 13:34:23.271","category":"object","action":"edit",'
    '"actor":{"name":"analyst1","roles":["admin","power","user"]},'
    '"result":"success","data":{"name":"my_search","type":"saved_search",'
    '"acl":{"read":[],"write":[]},"ownership":{"owner":"analyst1","app":"search"},'
    '"attributes":{"actions":"email","type":"scheduled","disabled":"false"}}}'
)
_UNPARSEABLE = "not an audit line"


def _rows(*raws: str) -> list[dict[str, Any]]:
    return [
        {"_raw": raw, "_time": f"2026-07-02T19:0{i}:00.000+07:00"}
        for i, raw in enumerate(raws)
    ]


def _role_entity(
    name: str,
    *,
    imported_roles: Any = (),
    capabilities: Any = (),
    srch_indexes_allowed: Any = (),
) -> MagicMock:
    role = MagicMock()
    role.name = name
    role.content = {
        "imported_roles": list(imported_roles),
        "capabilities": list(capabilities),
        "srchIndexesAllowed": list(srch_indexes_allowed),
    }
    return role


def _user_entity(name: str, *, roles: Any = (), email: str = "") -> MagicMock:
    """``roles`` is passed through as-is (list or bare str) to exercise both."""
    user = MagicMock()
    user.name = name
    user.content = {
        "roles": list(roles) if isinstance(roles, (list, tuple)) else roles,
        "email": email,
    }
    return user


# --- audit changes: SPL safety (acceptance #4) ---


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_spl_is_the_constant_string_regardless_of_filters(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    svc = MagicMock()
    mock_gc.return_value.service = svc
    mock_read.return_value = []

    CliRunner().invoke(
        cli,
        [
            "audit",
            "changes",
            "--user",
            'evil" | delete',
            "--action",
            "x | delete",
            "--object-type",
            "y] | rm -rf",
            "--since",
            "-1h | evil",
        ],
    )
    spl = svc.jobs.oneshot.call_args.args[0]
    assert spl == "search index=_audit"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_time_bounds_go_through_kwargs_not_spl(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    svc = MagicMock()
    mock_gc.return_value.service = svc
    mock_read.return_value = []

    CliRunner().invoke(cli, ["audit", "changes", "--since", "-7d", "--until", "-1d"])
    _, kwargs = svc.jobs.oneshot.call_args
    assert kwargs["earliest_time"] == "-7d"
    assert kwargs["latest_time"] == "-1d"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_defaults(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    svc = MagicMock()
    mock_gc.return_value.service = svc
    mock_read.return_value = []

    CliRunner().invoke(cli, ["audit", "changes"])
    _, kwargs = svc.jobs.oneshot.call_args
    assert kwargs["earliest_time"] == "-24h"
    assert kwargs["latest_time"] == "now"
    assert kwargs["count"] == 0


# --- audit changes: normalization + filters ---


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_normalizes_both_shapes_to_six_key_schema(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(_LEGACY_NO_OBJECT, _JSON_OBJECT_EDIT)

    result = CliRunner().invoke(cli, ["--json", "audit", "changes"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 2
    for row in rows:
        assert list(row.keys()) == [
            "time",
            "user",
            "action",
            "object",
            "object_type",
            "app",
        ]

    by_action = {r["action"]: r for r in rows}
    assert by_action["list_all_objects"]["user"] == "analyst1"
    assert by_action["edit"]["object"] == "my_search"
    assert by_action["edit"]["object_type"] == "saved_search"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_unparseable_event_is_never_dropped(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(_LEGACY_NO_OBJECT, _UNPARSEABLE)

    result = CliRunner().invoke(cli, ["--json", "audit", "changes"])
    rows = json.loads(result.stdout)
    assert len(rows) == 2
    unparsed = next(r for r in rows if r["action"] == "unparsed")
    assert unparsed["object"] == _UNPARSEABLE


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_user_filter_is_exact_match(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(_LEGACY_NO_OBJECT, _LEGACY_WITH_OBJECT)

    result = CliRunner().invoke(
        cli, ["--json", "audit", "changes", "--user", "analyst2"]
    )
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["user"] == "analyst2"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_action_filter_is_substring_match(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(_LEGACY_NO_OBJECT, _LEGACY_WITH_OBJECT)

    result = CliRunner().invoke(cli, ["--json", "audit", "changes", "--action", "edit"])
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["action"] == "edit_user"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_object_type_filter(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(_JSON_OBJECT_EDIT, _LEGACY_NO_OBJECT)

    result = CliRunner().invoke(
        cli, ["--json", "audit", "changes", "--object-type", "saved_search"]
    )
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["object_type"] == "saved_search"


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_limit_applies_after_filtering(
    mock_gc: MagicMock, mock_read: MagicMock
) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = _rows(*([_LEGACY_NO_OBJECT] * 5))

    result = CliRunner().invoke(cli, ["--json", "audit", "changes", "--limit", "2"])
    rows = json.loads(result.stdout)
    assert len(rows) == 2


@patch(_READ_RESULTS)
@patch(_PATCH)
def test_changes_empty_results(mock_gc: MagicMock, mock_read: MagicMock) -> None:
    mock_gc.return_value.service = MagicMock()
    mock_read.return_value = []

    result = CliRunner().invoke(cli, ["--format", "table", "audit", "changes"])
    assert result.exit_code == 0
    assert "No audit events found" in result.stderr


# --- audit rbac ---


@patch(_PATCH)
def test_rbac_per_user_aggregates_capabilities_across_imported_roles(
    mock_gc: MagicMock,
) -> None:
    svc = MagicMock()
    svc.roles = [
        _role_entity("user", capabilities=["search"], srch_indexes_allowed=["main"]),
        _role_entity(
            "power",
            imported_roles=["user"],
            capabilities=["rtsearch"],
            srch_indexes_allowed=["*"],
        ),
        _role_entity(
            "soc_analyst",
            imported_roles=["power"],
            capabilities=["edit_own_objects"],
            srch_indexes_allowed=["_audit"],
        ),
    ]
    svc.users = [_user_entity("jdoe", roles=["soc_analyst"], email="jdoe@example.com")]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--json", "audit", "rbac"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    row = rows[0]
    assert list(row.keys()) == [
        "user",
        "email",
        "roles",
        "capabilities",
        "srch_indexes_allowed",
    ]
    assert row["user"] == "jdoe"
    assert row["email"] == "jdoe@example.com"
    assert row["roles"] == "soc_analyst"
    # aggregated transitively: soc_analyst -> power -> user
    assert row["capabilities"] == "edit_own_objects;rtsearch;search"
    assert row["srch_indexes_allowed"] == "*;_audit;main"


@patch(_PATCH)
def test_rbac_dedups_capabilities_shared_across_roles(mock_gc: MagicMock) -> None:
    svc = MagicMock()
    svc.roles = [
        _role_entity("role_a", capabilities=["search", "list_settings"]),
        _role_entity("role_b", capabilities=["list_settings", "edit_own_objects"]),
    ]
    svc.users = [_user_entity("multi", roles=["role_a", "role_b"])]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--json", "audit", "rbac"])
    rows = json.loads(result.stdout)
    assert rows[0]["capabilities"] == "edit_own_objects;list_settings;search"


@patch(_PATCH)
def test_rbac_handles_bare_string_multivalue_fields(mock_gc: MagicMock) -> None:
    """Splunk's REST API sometimes returns a bare string for single-value fields."""
    svc = MagicMock()
    role = MagicMock()
    role.name = "solo_role"
    role.content = {
        "imported_roles": "power",
        "capabilities": "search",
        "srchIndexesAllowed": "main",
    }
    power = MagicMock()
    power.name = "power"
    power.content = {
        "imported_roles": "",
        "capabilities": "rtsearch",
        "srchIndexesAllowed": "*",
    }
    svc.roles = [role, power]
    svc.users = [_user_entity("solo", roles="solo_role")]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--json", "audit", "rbac"])
    rows = json.loads(result.stdout)
    assert rows[0]["roles"] == "solo_role"
    assert rows[0]["capabilities"] == "rtsearch;search"
    assert rows[0]["srch_indexes_allowed"] == "*;main"


@patch(_PATCH)
def test_rbac_roles_only_emits_one_row_per_role(mock_gc: MagicMock) -> None:
    svc = MagicMock()
    svc.roles = [
        _role_entity("user", capabilities=["search"], srch_indexes_allowed=["main"]),
        _role_entity(
            "power",
            imported_roles=["user"],
            capabilities=["rtsearch"],
            srch_indexes_allowed=["*"],
        ),
    ]
    mock_gc.return_value.service = svc

    # svc.users is never set on this mock; --roles-only must not touch it
    # (a TypeError on iterating a bare MagicMock would fail the assertion below).
    result = CliRunner().invoke(cli, ["--json", "audit", "rbac", "--roles-only"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    by_name = {r["role"]: r for r in rows}
    assert list(rows[0].keys()) == [
        "role",
        "imported_roles",
        "capabilities",
        "srch_indexes_allowed",
    ]
    assert by_name["power"]["imported_roles"] == "user"
    # power's own cap plus user's imported cap
    assert by_name["power"]["capabilities"] == "rtsearch;search"
    assert by_name["user"]["imported_roles"] == ""


@patch(_PATCH)
def test_rbac_csv_round_trips(mock_gc: MagicMock) -> None:
    svc = MagicMock()
    svc.roles = [
        _role_entity(
            "user",
            capabilities=["search", "list_settings"],
            srch_indexes_allowed=["main"],
        ),
    ]
    svc.users = [
        _user_entity("alice", roles=["user"], email="alice@example.com"),
        _user_entity("bob", roles=["user"], email="bob@example.com"),
    ]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--format", "csv", "audit", "rbac"])
    assert result.exit_code == 0
    reader = csv.DictReader(io.StringIO(result.stdout))
    parsed = list(reader)
    assert reader.fieldnames == [
        "user",
        "email",
        "roles",
        "capabilities",
        "srch_indexes_allowed",
    ]
    assert len(parsed) == 2
    assert parsed[0]["user"] == "alice"
    assert parsed[0]["capabilities"] == "list_settings;search"
    assert "\n" not in parsed[0]["capabilities"]


@patch(_PATCH)
def test_rbac_empty_users(mock_gc: MagicMock) -> None:
    svc = MagicMock()
    svc.roles = []
    svc.users = []
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--format", "table", "audit", "rbac"])
    assert result.exit_code == 0
    assert "No users found" in result.stderr


# --- commands --json self-discovery ---


def test_commands_json_includes_audit_group() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.output)
    names = [c["name"] for c in tree["commands"]]
    assert "audit" in names
    audit_node = next(c for c in tree["commands"] if c["name"] == "audit")
    sub_names = [c["name"] for c in audit_node["subcommands"]]
    assert set(sub_names) == {"changes", "rbac"}
    for sub in audit_node["subcommands"]:
        assert sub.get("guarded") is not True
