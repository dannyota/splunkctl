"""Unit tests for the ``_audit`` event-shape normalizer.

Fixtures below are redacted/renamed copies of REAL events pulled from the
local dev Splunk instance (`index=_audit`, both `audittrail` and
`audittrailv2` sourcetypes) — see the task report for the raw examples
and the mapping rationale.
"""

from splunkctl.commands.audit_parse import SCHEMA_KEYS, parse_event


def _row(raw: str, time: str = "2026-07-02T19:34:53.689+07:00") -> dict[str, str]:
    return {"_raw": raw, "_time": time}


# --- schema shape ---


def test_schema_keys_are_the_six_key_contract_in_order() -> None:
    assert SCHEMA_KEYS == ("time", "user", "action", "object", "object_type", "app")


def test_parsed_event_keys_always_match_schema_order() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 19:34:53.689, user=analyst1, "
        "action=list_all_objects, info=granted , cap=1]"
    )
    assert tuple(parse_event(row).keys()) == SCHEMA_KEYS


def test_time_always_comes_from_splunk_indexed_time_not_embedded_text() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 19:34:53.689, user=analyst1, "
        "action=list_all_objects, info=granted , cap=1]",
        time="2026-07-02T19:34:53.689+07:00",
    )
    assert parse_event(row)["time"] == "2026-07-02T19:34:53.689+07:00"


# --- legacy text shape (sourcetype=audittrail) ---


def test_legacy_capability_check_has_no_object_marker() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 19:34:53.689, user=analyst1, "
        "action=list_all_objects, info=granted , cap=1]"
    )
    result = parse_event(row)
    assert result["user"] == "analyst1"
    assert result["action"] == "list_all_objects"
    assert result["object"] == ""
    assert result["object_type"] == ""
    assert result["app"] == ""


def test_legacy_with_quoted_object_marker() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 19:15:29.443, user=analyst1, "
        'action=edit_user, info=granted object="jdoe" operation=list, cap=1]'
    )
    result = parse_event(row)
    assert result["user"] == "analyst1"
    assert result["action"] == "edit_user"
    assert result["object"] == "jdoe"
    assert result["object_type"] == ""


def test_legacy_edit_index_has_unquoted_app_and_no_object_marker() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 10:18:10.625, user=analyst1, "
        "action=edit_index, info=success, name=my_index, owner=nobody, "
        "app=search, modified_settings=[frozenTimePeriodInSecs=1, "
        "maxTotalDataSizeMB=500000]]"
    )
    result = parse_event(row)
    assert result["action"] == "edit_index"
    assert result["app"] == "search"
    # edit_index has no literal object="..." marker — object stays empty
    # even though the line does carry a name= field for this action.
    assert result["object"] == ""


def test_legacy_create_saved_search_has_quoted_app() -> None:
    row = _row(
        "Audit:[timestamp=07-02-2026 13:34:15.503, user=analyst1, "
        'action=create_saved_search, info=succeeded, savedsearch_name="my_search", '
        'app="search", owner="analyst1", disabled="false", type="scheduled"]'
    )
    result = parse_event(row)
    assert result["action"] == "create_saved_search"
    assert result["app"] == "search"
    assert result["object"] == ""


def test_legacy_artifact_deleted_has_no_info_field_at_all() -> None:
    """Live discovery: some system actions skip info= entirely."""
    row = _row(
        "Audit:[timestamp=07-02-2026 19:40:37.833, user=splunk-system-user, "
        "action=artifact_deleted, sid='SummaryDirector_1782995978.172', "
        "shc_managed=0, elapsed_ms=1, notify_captain=0]"
    )
    result = parse_event(row)
    assert result["user"] == "splunk-system-user"
    assert result["action"] == "artifact_deleted"
    assert result["object"] == ""


def test_legacy_file_integrity_update_has_no_info_and_no_space_after_action() -> None:
    """Live discovery: file-integrity update= has no info= and no space before path=."""
    row = _row(
        "Audit:[timestamp=07-02-2026 19:34:21.568, user=n/a, "
        'action=update,path="/opt/splunk/etc/system/local/web.conf", isdir=0, '
        'size=5362, gid=1004, uid=1001, modtime="Thu Jul  2 19:33:43 2026", '
        'mode="rw-------", hash=, chgs="modtime "]'
    )
    result = parse_event(row)
    assert result["user"] == "n/a"
    assert result["action"] == "update"
    assert result["object"] == ""


# --- structured JSON shape (sourcetype=audittrailv2) ---


def test_json_object_category_edit_maps_name_and_type() -> None:
    raw = (
        '{"timestamp":"07-02-2026 13:34:23.271","category":"object","action":"edit",'
        '"actor":{"name":"analyst1","roles":["admin","power","user"]},'
        '"result":"success","data":{"name":"my_search","type":"saved_search",'
        '"acl":{"read":[],"write":[]},"ownership":{"owner":"analyst1","app":"search"},'
        '"attributes":{"actions":"email","type":"scheduled","disabled":"false"}}}'
    )
    result = parse_event(_row(raw))
    assert result["user"] == "analyst1"
    assert result["action"] == "edit"
    assert result["object"] == "my_search"
    assert result["object_type"] == "saved_search"
    assert result["app"] == "search"


def test_json_system_category_account_edit_has_no_app() -> None:
    raw = (
        '{"timestamp":"07-02-2026 07:17:42.647","category":"system","action":"edit",'
        '"actor":{"name":"admin_svc","roles":["admin","power","user"]},'
        '"result":"success","data":{"name":"analyst2","type":"account",'
        '"attributes":{"roles":"power, user","is_user_locked":"true"}},'
        '"previous_data":{"attributes":{"roles":"user","is_user_locked":"false"}}}'
    )
    result = parse_event(_row(raw))
    assert result["user"] == "admin_svc"
    assert result["action"] == "edit"
    assert result["object"] == "analyst2"
    assert result["object_type"] == "account"
    assert result["app"] == ""  # account edits carry no ownership/app on this instance


def test_json_action_category_search_has_type_but_no_name() -> None:
    raw = (
        '{"timestamp":"07-02-2026 18:00:00.000","category":"action","action":"search",'
        '"actor":{"name":"analyst1","roles":["admin","power","user"]},'
        '"result":"success","data":{"type":"search",'
        '"attributes":{"search":"search index=_audit","app":"search"}}}'
    )
    result = parse_event(_row(raw))
    assert result["action"] == "search"
    assert result["object"] == ""
    assert result["object_type"] == "search"
    assert result["app"] == "search"


def test_json_authn_login_attempt_has_no_object_or_type() -> None:
    raw = (
        '{"timestamp":"07-02-2026 07:22:08.718","category":"authn",'
        '"action":"login_attempt","actor":{"name":"analyst1","roles":[]},'
        '"result":"success","data":{"attributes":{"client_ip":"10.0.0.5",'
        '"user":"analyst1","method":"Splunk"}}}'
    )
    result = parse_event(_row(raw))
    assert result["user"] == "analyst1"
    assert result["action"] == "login_attempt"
    assert result["object"] == ""
    assert result["object_type"] == ""
    assert result["app"] == ""


# --- unparseable: never dropped silently ---


def test_unparseable_line_becomes_unparsed_row_with_raw_in_object() -> None:
    raw = "totally not an audit line"
    result = parse_event(_row(raw))
    assert result["action"] == "unparsed"
    assert result["object"] == raw
    assert result["user"] == ""
    assert result["object_type"] == ""
    assert result["app"] == ""


def test_truncated_json_falls_back_to_unparsed() -> None:
    raw = '{"action": "edit", "actor": {"name": "x"'
    result = parse_event(_row(raw))
    assert result["action"] == "unparsed"
    assert result["object"] == raw


def test_json_missing_actor_and_action_is_unparsed() -> None:
    raw = '{"hello": "world"}'
    result = parse_event(_row(raw))
    assert result["action"] == "unparsed"


def test_empty_raw_is_unparsed_not_a_crash() -> None:
    result = parse_event({"_raw": "", "_time": "2026-07-02T00:00:00+00:00"})
    assert result["action"] == "unparsed"
    assert result["object"] == ""
