"""Tests for detection-as-code import/export."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules_io.get_client"


def _mock_ss(
    name: str,
    spl: str = "search index=main",
    *,
    cron: str = "",
    app: str = "search",
    disabled: str = "0",
    description: str = "",
) -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": spl,
        "description": description,
        "cron_schedule": cron,
        "is_scheduled": "1" if cron else "0",
        "disabled": disabled,
        "actions": "",
        "alert_type": "",
        "alert.severity": "",
        "alert.suppress": "",
        "alert.suppress.period": "",
        "alert.suppress.fields": "",
        "alert.track": "",
        "dispatch.earliest_time": "-24h",
        "dispatch.latest_time": "now",
    }
    ss.access = {"app": app}
    return ss


@patch(_PATCH)
def test_export_rules(mock_gc: MagicMock, tmp_path: MagicMock) -> None:
    svc = MagicMock()
    svc.saved_searches.list.return_value = [
        _mock_ss("detect_brute", "search index=auth | stats count by src"),
        _mock_ss("detect_c2", "search index=proxy", cron="*/5 * * * *"),
    ]
    mock_gc.return_value.service = svc

    out = tmp_path / "rules.yml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rules", "export", "--path", str(out)],
    )
    assert result.exit_code == 0
    assert "Exported 2 rule(s)" in result.output

    docs = yaml.safe_load(out.read_text())
    assert len(docs) == 2
    assert docs[0]["name"] == "detect_brute"
    assert docs[1]["cron_schedule"] == "*/5 * * * *"


@patch(_PATCH)
def test_export_specific_rule(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = _mock_ss(
        "my_rule", "search index=main error"
    )
    mock_gc.return_value.service = svc

    out = tmp_path / "one.yml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rules", "export", "--path", str(out), "--name", "my_rule"],
    )
    assert result.exit_code == 0
    docs = yaml.safe_load(out.read_text())
    assert len(docs) == 1
    assert docs[0]["name"] == "my_rule"


@patch(_PATCH)
def test_import_dry_run(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.dump(
            [
                {
                    "name": "new_rule",
                    "search": "search index=main error",
                    "cron_schedule": "*/10 * * * *",
                },
            ]
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rules", "import", "--path", str(rules_file)],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output
    mock_gc.return_value.service.saved_searches.create.assert_not_called()


@patch(_PATCH)
def test_import_creates_new(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("not found")
    mock_gc.return_value.service = svc

    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.dump(
            [
                {
                    "name": "detect_lateral",
                    "search": "search index=win EventCode=4624",
                    "cron_schedule": "*/15 * * * *",
                    "description": "Lateral movement detection",
                },
            ]
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "rules", "import", "--path", str(rules_file)],
    )
    assert result.exit_code == 0
    assert "1 created" in result.output
    svc.saved_searches.create.assert_called_once()


@patch(_PATCH)
def test_import_updates_existing(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    ss = _mock_ss("existing_rule")
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(
        yaml.dump(
            [
                {
                    "name": "existing_rule",
                    "search": "search index=main updated=true",
                },
            ]
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "rules", "import", "--path", str(rules_file)],
    )
    assert result.exit_code == 0
    assert "1 updated" in result.output
    ss.update.assert_called_once()


@patch(_PATCH)
def test_import_no_update_skips(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = _mock_ss("old")
    mock_gc.return_value.service = svc

    rules_file = tmp_path / "rules.yml"
    rules_file.write_text(yaml.dump([{"name": "old", "search": "search index=main"}]))
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "rules",
            "import",
            "--path",
            str(rules_file),
            "--no-update",
        ],
    )
    assert result.exit_code == 0
    assert "1 unchanged" in result.output


@patch(_PATCH)
def test_import_invalid_yaml(
    mock_gc: MagicMock,
    tmp_path: MagicMock,
) -> None:
    rules_file = tmp_path / "bad.yml"
    rules_file.write_text("not: a: list: [")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "rules", "import", "--path", str(rules_file)],
    )
    assert result.exit_code != 0


@patch(_PATCH)
def test_export_includes_thresholds(mock_gc: MagicMock, tmp_path: Path) -> None:
    ss = _mock_ss("det_thresh", cron="*/5 * * * *")
    ss.content.update(
        {
            "alert_type": "number of events",
            "alert_comparator": "greater than",
            "alert_threshold": "5",
            "actions": "email",
            "action.email.to": "soc@example.com",
            "action.email.sendresults": "1",
        }
    )
    mock_gc.return_value.service.saved_searches.list.return_value = [ss]

    out = tmp_path / "rules.yml"
    result = CliRunner().invoke(cli, ["rules", "export", "--path", str(out)])
    assert result.exit_code == 0
    doc = yaml.safe_load(out.read_text())[0]
    assert doc["alert_comparator"] == "greater than"
    assert doc["alert_threshold"] == "5"
    assert doc["action.email.to"] == "soc@example.com"


@patch(_PATCH)
def test_import_passes_unknown_fields_through(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump(
            [
                {
                    "name": "new_rule",
                    "search": "index=x",
                    "alert_comparator": "greater than",
                    "alert_threshold": "5",
                    "alert_type": "number of events",
                    "action.email.to": "soc@example.com",
                }
            ]
        )
    )
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("new_rule")
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--yes", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output
    _, kwargs = svc.saved_searches.create.call_args
    assert kwargs["alert_comparator"] == "greater than"
    assert kwargs["alert_threshold"] == "5"
    assert kwargs["action.email.to"] == "soc@example.com"


@patch(_PATCH)
def test_import_unchanged_skips_update(mock_gc: MagicMock, tmp_path: Path) -> None:
    ss = _mock_ss("same_rule", "index=x")
    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "same_rule", "search": "index=x"}]))
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--yes", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0
    assert "1 unchanged" in result.stderr
    ss.update.assert_not_called()


@patch(_PATCH)
def test_import_named_skip_exits_nonzero(mock_gc: MagicMock, tmp_path: Path) -> None:
    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump(
            [
                {"name": "broken_rule"},
                {"name": "good_rule", "search": "index=x"},
            ]
        )
    )
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("nope")
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--yes", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 1
    assert "broken_rule" in result.stderr
    assert "no search field" in result.stderr


@patch(_PATCH)
def test_import_dry_run_shows_field_diff(mock_gc: MagicMock, tmp_path: Path) -> None:
    ss = _mock_ss("det1", "index=old")
    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump([{"name": "det1", "search": "index=new", "alert_threshold": "9"}])
    )
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["rules", "import", "--path", str(yml)])
    assert result.exit_code == 0
    assert "update: det1" in result.stderr
    assert "index=old -> index=new" in result.stderr
    assert "alert_threshold" in result.stderr
    ss.update.assert_not_called()
