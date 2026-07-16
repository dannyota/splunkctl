"""Tests for state-io rules, parsers, and macros adapters."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from splunkctl.commands import state_io

# --------------------------------------------------------------------------
# mock helpers
# --------------------------------------------------------------------------


def _mock_ss(
    name: str,
    spl: str = "search index=main",
    *,
    cron: str = "",
    app: str = "search",
) -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": spl,
        "description": "",
        "cron_schedule": cron,
        "is_scheduled": "1" if cron else "0",
        "disabled": "0",
        "actions": "",
        "alert_type": "",
        "alert.severity": "",
    }
    ss.access = {"app": app}
    return ss


def _configs_resp(content: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps({"entry": [{"content": content}]}).encode()
    return resp


def _mock_stanza(name: str, app: str = "search") -> MagicMock:
    s = MagicMock()
    s.name = name
    s.access = {"app": app, "sharing": "app"}
    s.content = {}
    return s


def _client(svc: MagicMock) -> MagicMock:
    client = MagicMock()
    client.service = svc
    return client


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------


def test_pull_rules_writes_yaml(tmp_path: Path) -> None:
    svc = MagicMock()
    svc.saved_searches.list.return_value = [_mock_ss("det1", "index=main")]
    client = _client(svc)

    count = state_io.pull_rules(client, tmp_path, None)
    assert count == 1
    docs = yaml.safe_load((tmp_path / "rules.yml").read_text())
    assert docs[0]["name"] == "det1"


def test_pull_rules_filters_by_app(tmp_path: Path) -> None:
    svc = MagicMock()
    svc.saved_searches.list.return_value = [
        _mock_ss("det1", app="search"),
        _mock_ss("det2", app="other_app"),
    ]
    client = _client(svc)

    count = state_io.pull_rules(client, tmp_path, "other_app")
    assert count == 1
    docs = yaml.safe_load((tmp_path / "rules.yml").read_text())
    assert docs[0]["name"] == "det2"


def test_diff_rules_classifies_added_modified_unchanged_removed(tmp_path: Path) -> None:
    (tmp_path / "rules.yml").write_text(
        yaml.dump(
            [
                {"name": "new_rule", "search": "index=new"},
                {"name": "changed_rule", "search": "index=changed"},
                {"name": "same_rule", "search": "index=same"},
            ]
        )
    )
    svc = MagicMock()
    live = {
        "changed_rule": _mock_ss("changed_rule", "index=old"),
        "same_rule": _mock_ss("same_rule", "index=same"),
        "extra_rule": _mock_ss("extra_rule", "index=extra"),
    }

    def _getitem(name: str) -> MagicMock:
        if name not in live:
            raise KeyError(name)
        return live[name]

    svc.saved_searches.__getitem__.side_effect = _getitem
    svc.saved_searches.list.return_value = list(live.values())
    client = _client(svc)

    entries = {e["name"]: e for e in state_io.diff_rules(client, tmp_path, None)}
    assert entries["new_rule"]["change"] == "added"
    assert entries["changed_rule"]["change"] == "modified"
    assert entries["same_rule"]["change"] == "unchanged"
    assert entries["extra_rule"]["change"] == "removed"


def test_apply_rules_only_touches_added_and_modified(tmp_path: Path) -> None:
    (tmp_path / "rules.yml").write_text(
        yaml.dump(
            [
                {"name": "new_rule", "search": "index=new"},
                {"name": "same_rule", "search": "index=same"},
            ]
        )
    )
    svc = MagicMock()
    live = {"same_rule": _mock_ss("same_rule", "index=same")}

    def _getitem(name: str) -> MagicMock:
        if name not in live:
            raise KeyError(name)
        return live[name]

    svc.saved_searches.__getitem__.side_effect = _getitem
    client = _client(svc)

    records = state_io.apply_rules(client, tmp_path, None)
    assert [r["name"] for r in records] == ["new_rule"]
    assert records[0]["change"] == "added"
    assert records[0]["before"] is None
    assert records[0]["after"]["search"] == "index=new"
    svc.saved_searches.create.assert_called_once()


def test_apply_rules_never_deletes_removed_objects(tmp_path: Path) -> None:
    """A live rule absent from disk is never touched by apply."""
    (tmp_path / "rules.yml").write_text(yaml.dump([]))
    svc = MagicMock()
    live_rule = _mock_ss("only_live", "index=x")
    svc.saved_searches.list.return_value = [live_rule]
    client = _client(svc)

    records = state_io.apply_rules(client, tmp_path, None)
    assert records == []
    live_rule.delete.assert_not_called()


# --------------------------------------------------------------------------
# parsers
# --------------------------------------------------------------------------


def test_pull_parsers_writes_explicit_keys(tmp_path: Path) -> None:
    svc = MagicMock()
    conf = MagicMock()
    conf.list.return_value = [_mock_stanza("acme:fw")]
    svc.confs.__getitem__.return_value = conf
    svc.get.return_value = _configs_resp({"TIME_FORMAT": "%s", "eai:appName": "search"})
    client = _client(svc)

    count = state_io.pull_parsers(client, tmp_path, None)
    assert count == 2  # same stanza fetched once per conf (props, transforms)
    docs = yaml.safe_load((tmp_path / "parsers.yml").read_text())
    assert docs[0]["keys"] == {"TIME_FORMAT": "%s"}


def test_diff_parsers_added(tmp_path: Path) -> None:
    (tmp_path / "parsers.yml").write_text(
        yaml.dump(
            [
                {
                    "conf": "props",
                    "stanza": "new_st",
                    "app": "search",
                    "keys": {"TIME_FORMAT": "%s"},
                }
            ]
        )
    )
    svc = MagicMock()
    conf = MagicMock()
    conf.list.return_value = []
    svc.confs.__getitem__.return_value = conf
    svc.get.side_effect = Exception("404")
    client = _client(svc)

    entries = state_io.diff_parsers(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["change"] == "added"
    assert entries[0]["name"] == "props:new_st"


def test_apply_parsers_creates_and_updates(tmp_path: Path) -> None:
    (tmp_path / "parsers.yml").write_text(
        yaml.dump(
            [
                {
                    "conf": "props",
                    "stanza": "new_st",
                    "app": "search",
                    "sharing": "app",
                    "keys": {"TIME_FORMAT": "%s"},
                }
            ]
        )
    )
    svc = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("new_st")
    svc.confs.__getitem__.return_value = conf
    svc.get.side_effect = Exception("404")
    client = _client(svc)

    records = state_io.apply_parsers(client, tmp_path, None)
    assert len(records) == 1
    assert records[0]["change"] == "added"
    conf.create.assert_called_once()


# --------------------------------------------------------------------------
# macros
# --------------------------------------------------------------------------


def test_pull_macros_writes_explicit_keys(tmp_path: Path) -> None:
    svc = MagicMock()
    conf = MagicMock()
    conf.list.return_value = [_mock_stanza("my_macro")]
    svc.confs.__getitem__.return_value = conf
    svc.get.return_value = _configs_resp({"definition": "index=main"})
    client = _client(svc)

    count = state_io.pull_macros(client, tmp_path, None)
    assert count == 1
    docs = yaml.safe_load((tmp_path / "macros.yml").read_text())
    assert docs[0] == {
        "name": "my_macro",
        "app": "search",
        "keys": {"definition": "index=main"},
    }


def test_diff_macros_modified(tmp_path: Path) -> None:
    (tmp_path / "macros.yml").write_text(
        yaml.dump(
            [{"name": "my_macro", "app": "search", "keys": {"definition": "index=new"}}]
        )
    )
    svc = MagicMock()
    conf = MagicMock()
    conf.list.return_value = [_mock_stanza("my_macro")]
    svc.confs.__getitem__.return_value = conf
    svc.get.return_value = _configs_resp({"definition": "index=old"})
    client = _client(svc)

    entries = state_io.diff_macros(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["change"] == "modified"
    assert entries[0]["fields"] == [
        {"field": "definition", "old": "index=old", "new": "index=new"}
    ]


def _write_macro_doc(tmp_path: Path, app: str, definition: str) -> None:
    doc = [{"name": "my_macro", "app": app, "keys": {"definition": definition}}]
    (tmp_path / "macros.yml").write_text(yaml.dump(doc))


def test_apply_macros_create_uses_macros_own_app(tmp_path: Path) -> None:
    """A macro absent live is created under ITS OWN app, not the CLI's
    (unscoped) push default."""
    _write_macro_doc(tmp_path, "Splunk_Security_Essentials", "index=main")
    svc = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    svc.confs.__getitem__.return_value = conf
    svc.get.side_effect = Exception("404")
    client = _client(svc)

    records = state_io.apply_macros(client, tmp_path, None)  # unscoped push
    assert records[0]["change"] == "added"
    assert conf.create.call_args.kwargs.get("app") == "Splunk_Security_Essentials"


def test_apply_macros_update_uses_macros_own_app(tmp_path: Path) -> None:
    """A macro present live is updated in ITS OWN app's namespace."""
    _write_macro_doc(tmp_path, "Splunk_Security_Essentials", "index=new")
    svc = MagicMock()
    conf = MagicMock()
    live_stanza = MagicMock()
    conf.__getitem__.return_value = live_stanza
    svc.confs.__getitem__.return_value = conf
    svc.get.return_value = _configs_resp({"definition": "index=old"})
    client = _client(svc)

    records = state_io.apply_macros(client, tmp_path, None)  # unscoped push
    assert records[0]["change"] == "modified"
    live_stanza.update.assert_called_once_with(definition="index=new")
    namespace = conf.__getitem__.call_args.args[0][1]
    assert namespace.app == "Splunk_Security_Essentials"


def test_apply_macros_unscoped_push_targets_doc_app_not_default(tmp_path: Path) -> None:
    """Regression guard: unscoped push (`--app` omitted, `app=None`) must
    target the macro's OWN recorded app, not the connection's default
    namespace. RED against `conf_ops.set_keys(..., app=app)`."""
    _write_macro_doc(tmp_path, "some_app", "index=x")
    svc = MagicMock()
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("my_macro")
    svc.confs.__getitem__.return_value = conf
    svc.get.side_effect = Exception("404")
    client = _client(svc)

    records = state_io.apply_macros(client, tmp_path, None)
    assert records[0]["change"] == "added"
    assert conf.create.call_args.kwargs.get("app") == "some_app"
