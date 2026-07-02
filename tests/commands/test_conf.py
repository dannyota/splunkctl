"""Tests for the generic `conf` command group."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.conf.get_client"


def _file(name: str) -> MagicMock:
    f = MagicMock()
    f.name = name
    return f


def _stanza(name: str, content: dict[str, str], app: str = "search") -> MagicMock:
    s = MagicMock()
    s.name = name
    s.content = content
    s.access = {"app": app}
    return s


# --- files ---


@patch(_PATCH)
def test_files_lists_conf_files(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.confs.list.return_value = [_file("macros"), _file("props")]

    result = CliRunner().invoke(cli, ["--json", "conf", "files"])
    assert result.exit_code == 0, result.output
    names = [r["name"] for r in json.loads(result.output)]
    assert names == ["macros", "props"]


@patch(_PATCH)
def test_files_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.confs.list.return_value = []

    result = CliRunner().invoke(cli, ["--json", "conf", "files"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@patch(_PATCH)
def test_files_app_scoping(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.confs.list.return_value = [_file("macros")]

    result = CliRunner().invoke(
        cli, ["--json", "conf", "files", "--app", "Splunk_Security_Essentials"]
    )
    assert result.exit_code == 0
    svc.confs.list.assert_called_once_with(app="Splunk_Security_Essentials", owner="-")


@patch(_PATCH)
def test_files_no_app_scoping_by_default(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.confs.list.return_value = [_file("macros")]

    result = CliRunner().invoke(cli, ["--json", "conf", "files"])
    assert result.exit_code == 0
    svc.confs.list.assert_called_once_with()


@patch(_PATCH)
def test_files_filter(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.confs.list.return_value = [_file("macros"), _file("props")]

    result = CliRunner().invoke(cli, ["--json", "conf", "files", "--filter", "mac"])
    assert result.exit_code == 0
    names = [r["name"] for r in json.loads(result.output)]
    assert names == ["macros"]


# --- list ---


@patch(_PATCH)
def test_list_lists_stanzas(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.list.return_value = [_stanza("my_macro", {"definition": "index=main"})]
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["--json", "conf", "list", "macros"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert rows[0]["name"] == "my_macro"
    assert rows[0]["app"] == "search"
    svc.confs.__getitem__.assert_called_with("macros")


@patch(_PATCH)
def test_list_app_scoping(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.list.return_value = []
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli,
        ["--json", "conf", "list", "macros", "--app", "Splunk_Security_Essentials"],
    )
    assert result.exit_code == 0
    conf.list.assert_called_once_with(app="Splunk_Security_Essentials", owner="-")


@patch(_PATCH)
def test_list_filter_narrows(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.list.return_value = [
        _stanza("alpha_macro", {}),
        _stanza("beta_macro", {}),
    ]
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli, ["--json", "conf", "list", "macros", "--filter", "alpha"]
    )
    rows = json.loads(result.output)
    assert [r["name"] for r in rows] == ["alpha_macro"]


# --- get ---


@patch(_PATCH)
def test_get_full_stanza(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.return_value = _stanza(
        "my_macro", {"definition": "index=main", "args": ""}
    )
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["--json", "conf", "get", "macros", "my_macro"])
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["name"] == "my_macro"
    assert row["definition"] == "index=main"


@patch(_PATCH)
def test_get_single_key(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.return_value = _stanza("my_macro", {"definition": "index=main"})
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli, ["--json", "conf", "get", "macros", "my_macro", "--key", "definition"]
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row == {"name": "my_macro", "definition": "index=main"}


@patch(_PATCH)
def test_get_missing_key_returns_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.return_value = _stanza("my_macro", {"definition": "index=main"})
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli, ["--json", "conf", "get", "macros", "my_macro", "--key", "nope"]
    )
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row == {"name": "my_macro", "nope": ""}


@patch(_PATCH)
def test_get_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("nope")
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["conf", "get", "macros", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


# --- set ---


@patch(_PATCH)
def test_set_dry_run_shows_add_diff_for_new_stanza(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("agenttest_h1")
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli,
        ["conf", "set", "macros", "agenttest_h1", "definition=index=main"],
    )
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "add -> index=main" in result.output
    assert "macros" in result.output
    assert "agenttest_h1" in result.output
    conf.create.assert_not_called()


@patch(_PATCH)
def test_set_dry_run_shows_changed_diff_for_existing_stanza(
    mock_gc: MagicMock,
) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.return_value = _stanza("my_macro", {"definition": "index=old"})
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli,
        ["conf", "set", "macros", "my_macro", "definition=index=new"],
    )
    assert result.exit_code == 0, result.output
    assert "index=old -> index=new" in result.output


@patch(_PATCH)
def test_set_applies_with_yes_creates_stanza(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    created = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("agenttest_h1")
    conf.create.return_value = created
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli,
        ["--yes", "conf", "set", "macros", "agenttest_h1", "definition=index=main"],
    )
    assert result.exit_code == 0, result.output
    conf.create.assert_called_once_with("agenttest_h1", definition="index=main")


@patch(_PATCH)
def test_set_applies_with_yes_updates_existing(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    stanza = _stanza("my_macro", {"definition": "index=old"})
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli,
        ["--yes", "conf", "set", "macros", "my_macro", "definition=index=new"],
    )
    assert result.exit_code == 0, result.output
    stanza.update.assert_called_once_with(definition="index=new")


@patch(_PATCH)
def test_set_invalid_pair_rejected(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli, ["--yes", "conf", "set", "macros", "my_macro", "NOEQUALS"]
    )
    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output + result.stderr


# --- unset ---


@patch(_PATCH)
def test_unset_dry_run_shows_removal_diff(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.return_value = _stanza("my_macro", {"definition": "index=main"})
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli, ["conf", "unset", "macros", "my_macro", "definition"]
    )
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "index=main" in result.output


@patch(_PATCH)
def test_unset_applies_with_yes(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    stanza = _stanza("my_macro", {"definition": "index=main"})
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(
        cli, ["--yes", "conf", "unset", "macros", "my_macro", "definition"]
    )
    assert result.exit_code == 0, result.output
    stanza.update.assert_called_once_with(definition="")


@patch(_PATCH)
def test_unset_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("nope")
    svc.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["conf", "unset", "macros", "nope", "definition"])
    assert result.exit_code != 0
    assert "not found" in result.output


# --- reload ---


@patch(_PATCH)
def test_reload_dry_run(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    result = CliRunner().invoke(cli, ["conf", "reload", "macros"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    svc.post.assert_not_called()


@patch(_PATCH)
def test_reload_applies_with_yes(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    result = CliRunner().invoke(cli, ["--yes", "conf", "reload", "macros"])
    assert result.exit_code == 0, result.output
    svc.post.assert_called_once_with("/services/configs/conf-macros/_reload")


# --- self-discovery ---


def test_commands_json_includes_conf_group_with_guard_markers() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    conf = next(c for c in data["commands"] if c["name"] == "conf")
    subs = {s["name"]: s for s in conf["subcommands"]}
    assert set(subs) == {"files", "list", "get", "set", "unset", "reload"}
    for guarded in ("set", "unset", "reload"):
        assert subs[guarded].get("guarded") is True
    for unguarded in ("files", "list", "get"):
        assert "guarded" not in subs[unguarded]
