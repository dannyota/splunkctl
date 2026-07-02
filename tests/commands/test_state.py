"""Tests for the `state` command group (Task I1: unified config-as-code)."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.state.get_client"


def _mock_ss(
    name: str, spl: str = "search index=main", *, app: str = "search"
) -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": spl,
        "description": "",
        "cron_schedule": "",
        "is_scheduled": "0",
        "disabled": "0",
        "actions": "",
        "alert_type": "",
        "alert.severity": "",
    }
    ss.access = {"app": app}
    return ss


def _base_svc() -> MagicMock:
    svc = MagicMock()
    svc.host = "localhost"
    svc.port = 8089
    svc.saved_searches.list.return_value = []
    return svc


def _getitem_from(mapping: dict[str, MagicMock]) -> Any:
    def _get(name: str) -> MagicMock:
        if name not in mapping:
            raise KeyError(name)
        return mapping[name]

    return _get


@patch(_PATCH)
def test_pull_writes_tree_and_manifest(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = _base_svc()
    svc.saved_searches.list.return_value = [_mock_ss("det1")]
    mock_gc.return_value.service = svc

    target = tmp_path / "snap"
    result = CliRunner().invoke(
        cli, ["state", "pull", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output
    assert (target / "rules.yml").exists()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["types"] == {"rules": 1}
    assert manifest["host"] == "localhost:8089"
    assert "timestamp" not in manifest


@patch(_PATCH)
def test_pull_types_filter_skips_others(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = _base_svc()
    mock_gc.return_value.service = svc

    target = tmp_path / "snap"
    result = CliRunner().invoke(
        cli, ["state", "pull", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output
    assert not (target / "parsers.yml").exists()
    assert not (target / "macros.yml").exists()
    assert not (target / "lookups").exists()
    assert not (target / "dashboards").exists()


@patch(_PATCH)
def test_pull_rejects_unknown_type(mock_gc: MagicMock, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["state", "pull", "--dir", str(tmp_path / "snap"), "--types", "bogus"]
    )
    assert result.exit_code != 0
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_diff_json_array_payload(mock_gc: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(
        yaml.dump([{"name": "det1", "search": "index=new"}])
    )
    svc = _base_svc()
    ss = _mock_ss("det1", "index=old")
    svc.saved_searches.__getitem__.side_effect = _getitem_from({"det1": ss})
    svc.saved_searches.list.return_value = [ss]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "state", "diff", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert rows == [
        {
            "type": "rules",
            "name": "det1",
            "change": "modified",
            "fields": [{"field": "search", "old": "index=old", "new": "index=new"}],
        }
    ]


@patch(_PATCH)
def test_diff_exits_zero_with_drift(mock_gc: MagicMock, tmp_path: Path) -> None:
    """diff is a report, not a gate -- exit 0 regardless of drift."""
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(yaml.dump([]))
    svc = _base_svc()
    svc.saved_searches.list.return_value = [_mock_ss("only_live")]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["state", "diff", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output


@patch(_PATCH)
def test_push_dry_run_writes_report_applied_false(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(
        yaml.dump([{"name": "new_rule", "search": "index=x"}])
    )
    svc = _base_svc()
    svc.saved_searches.__getitem__.side_effect = KeyError("new_rule")
    mock_gc.return_value.service = svc

    report = tmp_path / "r.json"
    result = CliRunner().invoke(
        cli,
        [
            "state",
            "push",
            "--dir",
            str(target),
            "--types",
            "rules",
            "--report",
            str(report),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.stderr
    svc.saved_searches.create.assert_not_called()

    payload = json.loads(report.read_text())
    assert payload["applied"] is False
    assert payload["host"] == "localhost:8089"
    assert payload["types"] == ["rules"]
    assert payload["changes"][0]["name"] == "new_rule"
    assert payload["changes"][0]["change"] == "added"
    assert payload["changes"][0]["before"] is None
    assert payload["changes"][0]["after"]["search"] == "index=x"


@patch(_PATCH)
def test_push_yes_applies_and_writes_report_true(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(
        yaml.dump([{"name": "new_rule", "search": "index=x"}])
    )
    svc = _base_svc()
    svc.saved_searches.__getitem__.side_effect = KeyError("new_rule")
    mock_gc.return_value.service = svc

    report = tmp_path / "r.json"
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "state",
            "push",
            "--dir",
            str(target),
            "--types",
            "rules",
            "--report",
            str(report),
        ],
    )
    assert result.exit_code == 0, result.output
    svc.saved_searches.create.assert_called_once()

    payload = json.loads(report.read_text())
    assert payload["applied"] is True
    assert payload["changes"][0]["name"] == "new_rule"


@patch(_PATCH)
def test_push_without_report_flag_writes_nothing(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(yaml.dump([]))
    svc = _base_svc()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["state", "push", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output
    assert not list(tmp_path.glob("*.json"))


@patch(_PATCH)
def test_push_never_deletes_removed_object(mock_gc: MagicMock, tmp_path: Path) -> None:
    target = tmp_path / "snap"
    target.mkdir()
    (target / "rules.yml").write_text(yaml.dump([]))
    svc = _base_svc()
    live_only = _mock_ss("only_live")
    svc.saved_searches.list.return_value = [live_only]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "state", "push", "--dir", str(target), "--types", "rules"]
    )
    assert result.exit_code == 0, result.output
    live_only.delete.assert_not_called()
    svc.saved_searches.create.assert_not_called()


@patch(_PATCH)
def test_push_dashboards_apply_unsupported_no_error(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    target = tmp_path / "snap"
    (target / "dashboards").mkdir(parents=True)
    # locally edited -- differs from the live copy, so diff classifies it
    # "modified" (part of the apply plan) rather than "removed".
    (target / "dashboards" / "drifted_dash.xml").write_text("<a>edited</a>")
    svc = _base_svc()
    d = MagicMock()
    d.name = "drifted_dash"
    d.access = MagicMock()
    d.access.app = "search"
    d.content = {"isDashboard": True}
    d.export.return_value = "<a/>"
    svc.dashboards.list.return_value = [d]
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "state", "push", "--dir", str(target), "--types", "dashboards"]
    )
    assert result.exit_code == 0, result.output
    assert "apply not supported" in result.stderr.lower()


def test_commands_json_state_group_push_guard_marker() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    state = next(c for c in data["commands"] if c["name"] == "state")
    subs = {s["name"]: s for s in state["subcommands"]}
    assert set(subs) == {"pull", "diff", "push"}
    assert subs["push"].get("guarded") is True
    assert not subs["pull"].get("guarded")
    assert not subs["diff"].get("guarded")
