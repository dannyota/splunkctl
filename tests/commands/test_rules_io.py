"""Tests for detection-as-code import/export."""

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
