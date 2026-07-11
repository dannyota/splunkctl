"""Tests for macros/eventtypes/tags convenience verbs (knowledge.py)."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.knowledge.get_client"


def _stanza(name: str, content: dict[str, object], app: str = "search") -> MagicMock:
    s = MagicMock()
    s.name = name
    s.content = content
    s.access = {"app": app}
    return s


def _conf(mock_gc: MagicMock) -> MagicMock:
    """Wire ``get_client(ctx).service.confs[...]`` to a fresh conf mock."""
    conf = MagicMock()
    mock_gc.return_value.service.confs.__getitem__.return_value = conf
    return conf


# --- macros list ---


@patch(_PATCH)
def test_macros_list_shows_name_definition_args_app(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza(
            "Sort_MITRE_Rows(1)",
            {"definition": "eval x=$fieldname$", "args": "fieldname"},
            app="Splunk_Security_Essentials",
        )
    ]

    result = CliRunner().invoke(cli, ["--json", "macros", "list"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "Sort_MITRE_Rows(1)"
    assert row["definition"] == "eval x=$fieldname$"
    assert row["args"] == "fieldname"
    assert row["app"] == "Splunk_Security_Essentials"


@patch(_PATCH)
def test_macros_list_empty(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(cli, ["--json", "macros", "list"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@patch(_PATCH)
def test_macros_list_app_scoping(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(
        cli, ["macros", "list", "--app", "Splunk_Security_Essentials"]
    )
    assert result.exit_code == 0
    conf.list.assert_called_once_with(app="Splunk_Security_Essentials", owner="-")


@patch(_PATCH)
def test_macros_list_no_app_scoping_by_default(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(cli, ["macros", "list"])
    assert result.exit_code == 0
    conf.list.assert_called_once_with()


@patch(_PATCH)
def test_macros_list_filter_narrows(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza("alpha", {"definition": "a"}),
        _stanza("beta", {"definition": "b"}),
    ]

    result = CliRunner().invoke(cli, ["--json", "macros", "list", "--filter", "alpha"])
    rows = json.loads(result.output)
    assert [r["name"] for r in rows] == ["alpha"]


@patch(_PATCH)
def test_macros_list_definition_truncated_in_table_not_json(
    mock_gc: MagicMock,
) -> None:
    long_def = "x" * 200
    conf = _conf(mock_gc)
    conf.list.return_value = [_stanza("big_macro", {"definition": long_def})]

    result = CliRunner().invoke(cli, ["--json", "macros", "list"])
    assert long_def in result.output

    result = CliRunner().invoke(cli, ["--format", "table", "macros", "list"])
    assert result.exit_code == 0, result.output
    assert long_def not in result.output
    assert "chars]" in result.output


# --- macros get ---


@patch(_PATCH)
def test_macros_get_exact_no_arg_match(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.return_value = _stanza("Sort_MITRE", {"definition": "fields x"})

    result = CliRunner().invoke(cli, ["--json", "macros", "get", "Sort_MITRE"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "Sort_MITRE"
    assert row["definition"] == "fields x"
    conf.list.assert_not_called()


@patch(_PATCH)
def test_macros_get_resolves_bare_name_to_arg_form(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("Sort_MITRE_Rows")
    conf.list.return_value = [
        _stanza(
            "Sort_MITRE_Rows(1)",
            {"definition": "eval x=$fieldname$", "args": "fieldname"},
        ),
        _stanza("Other_Macro", {"definition": "y"}),
    ]

    result = CliRunner().invoke(cli, ["--json", "macros", "get", "Sort_MITRE_Rows"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "Sort_MITRE_Rows(1)"
    conf.__getitem__.assert_called_once_with("Sort_MITRE_Rows")


@patch(_PATCH)
def test_macros_get_multiple_arg_forms_picks_lowest_argcount(
    mock_gc: MagicMock,
) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("foo")
    conf.list.return_value = [
        _stanza("foo(2)", {"definition": "b"}),
        _stanza("foo(1)", {"definition": "a"}),
    ]

    result = CliRunner().invoke(cli, ["--json", "macros", "get", "foo"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "foo(1)"


@patch(_PATCH)
def test_macros_get_literal_arg_form_not_found_skips_fallback(
    mock_gc: MagicMock,
) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("Sort_MITRE_Rows(2)")

    result = CliRunner().invoke(cli, ["macros", "get", "Sort_MITRE_Rows(2)"])
    assert result.exit_code != 0
    assert "not found" in result.output
    conf.list.assert_not_called()


@patch(_PATCH)
def test_macros_get_no_match_anywhere_not_found(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")
    conf.list.return_value = [_stanza("unrelated(1)", {"definition": "x"})]

    result = CliRunner().invoke(cli, ["--json", "macros", "get", "nope"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"


# --- macros set ---


@patch(_PATCH)
def test_macros_set_dry_run_names_conf_and_stanza(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h2")

    result = CliRunner().invoke(
        cli, ["macros", "set", "agenttest_h2", "--definition", "index=main"]
    )
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "macros.conf" in result.output
    assert "agenttest_h2" in result.output
    assert "add -> index=main" in result.output
    conf.create.assert_not_called()


@patch(_PATCH)
def test_macros_set_no_args_delegates_to_conf_ops_set_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h2")

    with patch("splunkctl.commands.knowledge.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            ["--yes", "macros", "set", "agenttest_h2", "--definition", "index=main"],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "macros",
        "agenttest_h2",
        {"definition": "index=main"},
    )


@patch(_PATCH)
def test_macros_set_with_args_writes_arg_form_stanza(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("my_macro(2)")

    with patch("splunkctl.commands.knowledge.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "macros",
                "set",
                "my_macro",
                "--definition",
                "eval x=$a$+$b$",
                "--args",
                "a,b",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "macros",
        "my_macro(2)",
        {"definition": "eval x=$a$+$b$", "args": "a,b"},
    )


@patch(_PATCH)
def test_macros_set_requires_yes_to_apply(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h2")

    with patch("splunkctl.commands.knowledge.conf_ops.set_keys") as mock_set_keys:
        result = CliRunner().invoke(
            cli, ["macros", "set", "agenttest_h2", "--definition", "index=main"]
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_not_called()


# --- eventtypes list/get (read-only) ---


@patch(_PATCH)
def test_eventtypes_list_shows_name_search_app_disabled(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza(
            "cim:authentication",
            {"search": "action=* app=*", "disabled": False},
            app="Splunk_SA_CIM",
        )
    ]

    result = CliRunner().invoke(cli, ["--json", "eventtypes", "list"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "cim:authentication"
    assert row["search"] == "action=* app=*"
    assert row["app"] == "Splunk_SA_CIM"
    assert row["disabled"] is False


@patch(_PATCH)
def test_eventtypes_list_search_truncated_in_table(mock_gc: MagicMock) -> None:
    long_search = "index=main " * 20
    conf = _conf(mock_gc)
    conf.list.return_value = [_stanza("big_et", {"search": long_search})]

    result = CliRunner().invoke(cli, ["--format", "table", "eventtypes", "list"])
    assert result.exit_code == 0, result.output
    assert long_search.strip() not in result.output
    assert "chars]" in result.output


@patch(_PATCH)
def test_eventtypes_list_app_scoping(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(cli, ["eventtypes", "list", "--app", "my_app"])
    assert result.exit_code == 0
    conf.list.assert_called_once_with(app="my_app", owner="-")


@patch(_PATCH)
def test_eventtypes_get_full_stanza(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.return_value = _stanza(
        "cim:authentication",
        {
            "search": "action=* app=*",
            "priority": "5",
            "color": "none",
            "tags": "",
        },
    )

    result = CliRunner().invoke(
        cli, ["--json", "eventtypes", "get", "cim:authentication"]
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "cim:authentication"
    assert row["search"] == "action=* app=*"
    assert row["priority"] == "5"
    assert row["color"] == "none"


@patch(_PATCH)
def test_eventtypes_get_not_found(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(cli, ["eventtypes", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_eventtypes_group_has_no_mutation_commands() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    group = next(c for c in data["commands"] if c["name"] == "eventtypes")
    assert {s["name"] for s in group["subcommands"]} == {"list", "get"}


# --- tags list/get (read-only) ---


@patch(_PATCH)
def test_tags_list_enabled_tags_only_semicolon_joined(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza(
            "eventtype=cim%3Aauthentication",
            {
                "authentication": "enabled",
                "cim3": "enabled",
                "deprecated": "disabled",
                "disabled": False,
                "eai:appName": "search",
                "eai:userName": "splunk",
            },
            app="Splunk_SA_CIM",
        )
    ]

    result = CliRunner().invoke(cli, ["--json", "tags", "list"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["field_value"] == "eventtype=cim:authentication"
    assert row["app"] == "Splunk_SA_CIM"
    tags = row["tags"].split(";")
    assert set(tags) == {"authentication", "cim3"}
    assert "deprecated" not in tags


@patch(_PATCH)
def test_tags_list_app_scoping(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(cli, ["tags", "list", "--app", "my_app"])
    assert result.exit_code == 0
    conf.list.assert_called_once_with(app="my_app", owner="-")


@patch(_PATCH)
def test_tags_get_shows_all_tag_states(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.return_value = _stanza(
        "eventtype=cim%3Aauthentication",
        {
            "authentication": "enabled",
            "deprecated": "disabled",
            "disabled": False,
            "eai:appName": "search",
            "eai:userName": "splunk",
        },
    )

    result = CliRunner().invoke(
        cli, ["--json", "tags", "get", "eventtype=cim%3Aauthentication"]
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "eventtype=cim:authentication"
    assert row["authentication"] == "enabled"
    assert row["deprecated"] == "disabled"
    assert "eai:appName" not in row
    assert "disabled" not in row  # stanza-level disabled flag, not a tag


@patch(_PATCH)
def test_tags_get_accepts_decoded_stanza_name(mock_gc: MagicMock) -> None:
    """A human-readable field=value resolves via its URL-encoded stanza."""
    conf = _conf(mock_gc)
    encoded = "eventtype=cim%3Aauthentication"
    stanza = _stanza(encoded, {"authentication": "enabled"})

    def lookup(key: str) -> MagicMock:
        if key == encoded:
            return stanza
        raise KeyError(key)

    conf.__getitem__.side_effect = lookup

    result = CliRunner().invoke(
        cli, ["--json", "tags", "get", "eventtype=cim:authentication"]
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "eventtype=cim:authentication"
    assert row["authentication"] == "enabled"


@patch(_PATCH)
def test_tags_get_not_found(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("nope")

    result = CliRunner().invoke(cli, ["tags", "get", "field=value"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_tags_group_has_no_mutation_commands() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    group = next(c for c in data["commands"] if c["name"] == "tags")
    assert {s["name"] for s in group["subcommands"]} == {"list", "get"}


# --- self-discovery ---


def test_commands_json_includes_macros_group_with_guard_marker() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    macros = next(c for c in data["commands"] if c["name"] == "macros")
    subs = {s["name"]: s for s in macros["subcommands"]}
    assert set(subs) == {"list", "get", "set"}
    assert subs["set"].get("guarded") is True
    assert "guarded" not in subs["list"]
    assert "guarded" not in subs["get"]
