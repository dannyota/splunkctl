"""Tests for lookup-wiring pure helpers (splunkctl.commands.lookups_wiring).

No CLI/guard/SDK scaffolding here — these exercise the value-string and
kv-dict construction directly, so the LOOKUP-<class> grammar and the
transforms.conf key-building logic have a fast, focused test surface of
their own. CLI-level delegation/guard/validation behavior for `lookups
define`/`lookups auto` lives in test_lookups_define.py and test_lookups_auto.py.
"""

import click
import pytest

from splunkctl.commands.lookups_wiring import (
    build_lookup_value,
    build_transforms_kv,
    parse_field_spec,
)

# --- parse_field_spec ---


def test_parse_field_spec_no_rename() -> None:
    assert parse_field_spec("host") == ("host", None)


def test_parse_field_spec_with_rename() -> None:
    assert parse_field_spec("host:src_host") == ("host", "src_host")


def test_parse_field_spec_empty_left_raises() -> None:
    with pytest.raises(click.BadParameter):
        parse_field_spec(":renamed")


def test_parse_field_spec_empty_right_raises() -> None:
    with pytest.raises(click.BadParameter):
        parse_field_spec("host:")


def test_parse_field_spec_too_many_colons_raises() -> None:
    with pytest.raises(click.BadParameter):
        parse_field_spec("a:b:c")


# --- build_transforms_kv ---


def test_build_transforms_kv_file_only() -> None:
    kv = build_transforms_kv(
        file="agenttest_h4.csv",
        collection=None,
        max_matches=None,
        min_matches=None,
        case_sensitive=None,
        default_match=None,
    )
    assert kv == {"filename": "agenttest_h4.csv"}


def test_build_transforms_kv_collection_only() -> None:
    kv = build_transforms_kv(
        file=None,
        collection="my_collection",
        max_matches=None,
        min_matches=None,
        case_sensitive=None,
        default_match=None,
    )
    assert kv == {"external_type": "kvstore", "collection": "my_collection"}


def test_build_transforms_kv_optional_keys_included_when_given() -> None:
    kv = build_transforms_kv(
        file="x.csv",
        collection=None,
        max_matches=5,
        min_matches=1,
        case_sensitive=True,
        default_match="unknown",
    )
    assert kv == {
        "filename": "x.csv",
        "max_matches": "5",
        "min_matches": "1",
        "case_sensitive_match": "true",
        "default_match": "unknown",
    }


def test_build_transforms_kv_case_sensitive_false() -> None:
    kv = build_transforms_kv(
        file="x.csv",
        collection=None,
        max_matches=None,
        min_matches=None,
        case_sensitive=False,
        default_match=None,
    )
    assert kv["case_sensitive_match"] == "false"


def test_build_transforms_kv_optional_keys_omitted_when_not_given() -> None:
    kv = build_transforms_kv(
        file="x.csv",
        collection=None,
        max_matches=None,
        min_matches=None,
        case_sensitive=None,
        default_match=None,
    )
    assert "max_matches" not in kv
    assert "min_matches" not in kv
    assert "case_sensitive_match" not in kv
    assert "default_match" not in kv


# --- build_lookup_value ---


def test_build_lookup_value_acceptance_path_shape() -> None:
    """The exact stanza the H4 acceptance path expects to see written."""
    value = build_lookup_value("agenttest_h4_def", ("host",), ("col",), overwrite=True)
    assert value == "agenttest_h4_def host OUTPUT col"


def test_build_lookup_value_no_overwrite_uses_outputnew() -> None:
    value = build_lookup_value("mydef", ("host",), ("col",), overwrite=False)
    assert value == "mydef host OUTPUTNEW col"


def test_build_lookup_value_multi_input_multi_output() -> None:
    value = build_lookup_value(
        "mydef", ("host", "user"), ("col1", "col2"), overwrite=True
    )
    assert value == "mydef host user OUTPUT col1 col2"


def test_build_lookup_value_output_rename_is_direct() -> None:
    """--output lookup_field:event_field maps straight onto Splunk's own
    grammar (`<output_field> [AS <output_field_in_event>]`) -- no swap."""
    value = build_lookup_value(
        "mydef", ("host",), ("threat_level:risk_score",), overwrite=True
    )
    assert value == "mydef host OUTPUT threat_level AS risk_score"


def test_build_lookup_value_input_rename_is_swapped() -> None:
    """--input event_field:lookup_field is deliberately reversed from
    Splunk's own on-the-wire order (`<match_field> [AS <match_field_in_event>]`,
    lookup-table field first) so the CLI can take the event field --
    the one the operator already knows -- first, and only ask for the
    lookup table's column name when it actually differs."""
    value = build_lookup_value("mydef", ("host:hostname",), ("col",), overwrite=True)
    assert value == "mydef hostname AS host OUTPUT col"


def test_build_lookup_value_mixed_renamed_and_plain_inputs() -> None:
    value = build_lookup_value(
        "mydef", ("host:hostname", "user"), ("col",), overwrite=True
    )
    assert value == "mydef hostname AS host user OUTPUT col"
