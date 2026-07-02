"""Tests for `lookups define` and `lookups definitions`.

Covers the transforms.conf lookup-definition stanza: exactly-one-of
--file/--collection validation (exit 2), the non-blocking --file
existence warning, dry-run diff previews, delegation to
`conf_ops.set_keys` (the actual value-string/kv construction is unit
tested directly against `lookups_wiring` in test_lookups_wiring.py), the
guard, and the read-only `definitions` listing. `lookups auto` lives in
test_lookups_auto.py; `lookups.py`'s original list/get/upload/update/
download/delete commands stay in test_lookups.py.
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.lookups.get_client"


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


# --- lookups define: validation ---


def test_define_requires_file_or_collection() -> None:
    result = CliRunner().invoke(cli, ["lookups", "define", "agenttest_h4_def"])
    assert result.exit_code == 2
    assert "exactly one" in result.output.lower()


def test_define_rejects_both_file_and_collection() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "define",
            "agenttest_h4_def",
            "--file",
            "x.csv",
            "--collection",
            "x_coll",
        ],
    )
    assert result.exit_code == 2
    assert "exactly one" in result.output.lower()


# --- lookups define: dry run ---


@patch(_PATCH)
def test_define_dry_run_names_transforms_and_stanza(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "define",
            "agenttest_h4_def",
            "--file",
            "agenttest_h4.csv",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output
    assert "transforms.conf" in result.output
    assert "agenttest_h4_def" in result.output
    assert "filename: add -> agenttest_h4.csv" in result.output
    conf.create.assert_not_called()


@patch(_PATCH)
def test_define_collection_builds_kvstore_kv_in_diff(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_kv")

    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "define",
            "agenttest_h4_kv",
            "--collection",
            "agenttest_h4_coll",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "external_type: add -> kvstore" in result.output
    assert "collection: add -> agenttest_h4_coll" in result.output


@patch(_PATCH)
def test_define_dry_run_includes_optional_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    result = CliRunner().invoke(
        cli,
        [
            "lookups",
            "define",
            "agenttest_h4_def",
            "--file",
            "agenttest_h4.csv",
            "--max-matches",
            "5",
            "--min-matches",
            "1",
            "--case-sensitive",
            "--default-match",
            "unknown",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "max_matches: add -> 5" in result.output
    assert "min_matches: add -> 1" in result.output
    assert "case_sensitive_match: add -> true" in result.output
    assert "default_match: add -> unknown" in result.output


# --- lookups define: file-existence warning (non-blocking) ---


@patch(_PATCH)
def test_define_warns_when_file_not_found(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = []

    result = CliRunner().invoke(
        cli,
        ["lookups", "define", "agenttest_h4_def", "--file", "missing.csv"],
    )
    assert result.exit_code == 0, result.output
    assert "missing.csv" in result.output
    assert "not found" in result.output.lower()
    # Non-blocking: the dry-run preview still ran.
    assert "[DRY RUN]" in result.output


@patch(_PATCH)
def test_define_no_warning_when_file_exists(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    result = CliRunner().invoke(
        cli,
        ["lookups", "define", "agenttest_h4_def", "--file", "agenttest_h4.csv"],
    )
    assert result.exit_code == 0, result.output
    assert "not found" not in result.output.lower()


@patch(_PATCH)
def test_define_file_check_failure_never_blocks(mock_gc: MagicMock) -> None:
    """A broken lookup_table_files.list() call is swallowed -- best-effort
    only, never a hard failure for `define`."""
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.side_effect = RuntimeError(
        "boom"
    )

    result = CliRunner().invoke(
        cli, ["lookups", "define", "agenttest_h4_def", "--file", "agenttest_h4.csv"]
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output


# --- lookups define: delegation to conf_ops.set_keys ---


@patch(_PATCH)
def test_define_file_delegates_to_conf_ops_set_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "define",
                "agenttest_h4_def",
                "--file",
                "agenttest_h4.csv",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "transforms",
        "agenttest_h4_def",
        {"filename": "agenttest_h4.csv"},
        app=None,
    )
    assert "Created" in result.output


@patch(_PATCH)
def test_define_collection_delegates_to_conf_ops_set_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_kv")

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "define",
                "agenttest_h4_kv",
                "--collection",
                "agenttest_h4_coll",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "transforms",
        "agenttest_h4_kv",
        {"external_type": "kvstore", "collection": "agenttest_h4_coll"},
        app=None,
    )


@patch(_PATCH)
def test_define_app_option_scopes_lookup_and_set_keys(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        mock_set_keys.return_value = (MagicMock(), True)
        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "lookups",
                "define",
                "agenttest_h4_def",
                "--file",
                "agenttest_h4.csv",
                "--app",
                "my_app",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_called_once_with(
        mock_gc.return_value,
        "transforms",
        "agenttest_h4_def",
        {"filename": "agenttest_h4.csv"},
        app="my_app",
    )
    # The pre-check lookup also used the namespace tuple form.
    (key,), _kwargs = conf.__getitem__.call_args
    name, ns = key
    assert name == "agenttest_h4_def"
    assert ns.app == "my_app"


@patch(_PATCH)
def test_define_requires_yes_to_apply(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.__getitem__.side_effect = KeyError("agenttest_h4_def")
    mock_gc.return_value.service.lookup_table_files.list.return_value = [MagicMock()]

    with patch("splunkctl.commands.lookups.conf_ops.set_keys") as mock_set_keys:
        result = CliRunner().invoke(
            cli, ["lookups", "define", "agenttest_h4_def", "--file", "agenttest_h4.csv"]
        )
    assert result.exit_code == 0, result.output
    mock_set_keys.assert_not_called()


# --- lookups definitions (read-only listing) ---


@patch(_PATCH)
def test_definitions_lists_only_lookup_stanzas(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza("agenttest_h4_def", {"filename": "agenttest_h4.csv"}),
        _stanza("agenttest_h4_kv", {"external_type": "kvstore", "collection": "coll"}),
        _stanza("strip_headers", {"REGEX": "^#.*", "DEST_KEY": "queue"}),
    ]

    result = CliRunner().invoke(cli, ["--json", "lookups", "definitions"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    names = {r["name"] for r in rows}
    assert names == {"agenttest_h4_def", "agenttest_h4_kv"}


@patch(_PATCH)
def test_definitions_shows_file_or_collection_column(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = [
        _stanza("agenttest_h4_def", {"filename": "agenttest_h4.csv"}),
        _stanza("agenttest_h4_kv", {"external_type": "kvstore", "collection": "coll"}),
    ]

    result = CliRunner().invoke(cli, ["--json", "lookups", "definitions"])
    rows = {r["name"]: r for r in json.loads(result.output)}
    assert rows["agenttest_h4_def"]["filename"] == "agenttest_h4.csv"
    assert rows["agenttest_h4_kv"]["collection"] == "coll"


@patch(_PATCH)
def test_definitions_empty(mock_gc: MagicMock) -> None:
    conf = _conf(mock_gc)
    conf.list.return_value = []

    result = CliRunner().invoke(cli, ["--json", "lookups", "definitions"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


# --- commands --json markers ---


def test_commands_json_marks_define_and_auto_guarded() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0, result.output
    tree = json.loads(result.output)
    lookups_node = next(c for c in tree["commands"] if c["name"] == "lookups")
    by_name = {c["name"]: c for c in lookups_node["subcommands"]}
    assert by_name["define"].get("guarded") is True
    assert by_name["auto"].get("guarded") is True
    assert "definitions" in by_name
    assert by_name["definitions"].get("guarded") is not True
