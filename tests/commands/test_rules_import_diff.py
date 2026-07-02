"""Tests for `rules import` dry-run structured diff (Task E6)."""

import json
import re
from typing import Any
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


def _rows(output: str) -> list[dict[str, Any]]:
    data = json.loads(output)
    assert isinstance(data, list)
    return data


@patch(_PATCH)
def test_import_json_dry_run_create(mock_gc: MagicMock, tmp_path: Any) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("not found")
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump(
            [
                {
                    "name": "new_rule",
                    "search": "index=main error",
                    "cron_schedule": "*/10 * * * *",
                },
            ]
        )
    )
    result = CliRunner().invoke(cli, ["--json", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output
    svc.saved_searches.create.assert_not_called()

    rows = _rows(result.stdout)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "new_rule"
    assert row["action"] == "create"

    by_field = {c["field"]: c for c in row["changes"]}
    assert by_field["search"]["old"] is None
    assert by_field["search"]["new"] == "index=main error"
    assert by_field["cron_schedule"]["old"] is None
    assert by_field["cron_schedule"]["new"] == "*/10 * * * *"


@patch(_PATCH)
def test_import_json_dry_run_update_full_untruncated(
    mock_gc: MagicMock, tmp_path: Any
) -> None:
    long_old = "index=_internal error | stats count by sourcetype" + "x" * 80
    long_new = long_old + " | where count > 1"
    ss = _mock_ss("det1", long_old)
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump(
            [
                {"name": "det1", "search": long_new, "alert_threshold": "9"},
            ]
        )
    )
    result = CliRunner().invoke(cli, ["--json", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output
    ss.update.assert_not_called()

    rows = _rows(result.stdout)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "det1"
    assert row["action"] == "update"

    by_field = {c["field"]: c for c in row["changes"]}
    # full, untruncated values -- no ellipsis anywhere in the JSON payload
    assert by_field["search"]["old"] == long_old
    assert by_field["search"]["new"] == long_new
    assert "…" not in result.stdout
    assert by_field["alert_threshold"]["old"] == ""
    assert by_field["alert_threshold"]["new"] == "9"


@patch(_PATCH)
def test_import_json_dry_run_unchanged(mock_gc: MagicMock, tmp_path: Any) -> None:
    ss = _mock_ss("same_rule", "index=x")
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "same_rule", "search": "index=x"}]))
    result = CliRunner().invoke(cli, ["--json", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output

    rows = _rows(result.stdout)
    assert rows == [{"name": "same_rule", "action": "unchanged", "changes": []}]


@patch(_PATCH)
def test_import_json_dry_run_no_update_existing_reports_unchanged(
    mock_gc: MagicMock, tmp_path: Any
) -> None:
    """--no-update, rule already exists -> unchanged/empty (delegated call)."""
    ss = _mock_ss("old_rule", "index=x")
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "old_rule", "search": "index=y"}]))
    result = CliRunner().invoke(
        cli, ["--json", "rules", "import", "--path", str(yml), "--no-update"]
    )
    assert result.exit_code == 0, result.output

    rows = _rows(result.stdout)
    assert rows == [{"name": "old_rule", "action": "unchanged", "changes": []}]


@patch(_PATCH)
def test_import_json_dry_run_skip_invalid_entries(
    mock_gc: MagicMock, tmp_path: Any
) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("nope")
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(
        yaml.dump(
            [
                {"name": "no_search_rule"},
                {"search": "index=x"},  # no name at all
            ]
        )
    )
    result = CliRunner().invoke(cli, ["--json", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output

    rows = _rows(result.stdout)
    assert len(rows) == 2
    assert rows[0]["name"] == "no_search_rule"
    assert rows[0]["action"] == "skip"
    assert rows[0]["changes"] == []
    assert "no search field" in rows[0]["reason"]

    assert rows[1]["name"] is None
    assert rows[1]["action"] == "skip"
    assert "no name" in rows[1]["reason"]


@patch(_PATCH)
def test_import_json_dry_run_no_mutation(mock_gc: MagicMock, tmp_path: Any) -> None:
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("not found")
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "new_rule", "search": "index=x"}]))
    result = CliRunner().invoke(cli, ["--json", "rules", "import", "--path", str(yml)])
    assert result.exit_code == 0
    svc.saved_searches.create.assert_not_called()
    svc.saved_searches.__getitem__.return_value.update.assert_not_called()


@patch(_PATCH)
def test_import_text_dry_run_truncates_with_length_marker(
    mock_gc: MagicMock, tmp_path: Any
) -> None:
    long_old = "index=main " + "a" * 100
    long_new = long_old + " | stats count"
    ss = _mock_ss("det_long", long_old)
    svc = MagicMock()
    svc.saved_searches.__getitem__.return_value = ss
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "det_long", "search": long_new}]))
    result = CliRunner().invoke(cli, ["rules", "import", "--path", str(yml)])
    assert result.exit_code == 0
    ss.update.assert_not_called()

    text = result.stderr
    # never a bare ellipsis: every "…" must be immediately followed by
    # an explicit "[+N chars]" length marker
    assert not re.search(r"…(?! \[\+\d+ chars\])", text)
    assert re.search(r"… \[\+\d+ chars\]", text)


@patch(_PATCH)
def test_import_text_dry_run_no_json_payload_on_stdout(
    mock_gc: MagicMock, tmp_path: Any
) -> None:
    """Plain dry-run (no --json) keeps stdout clean; preview stays on stderr."""
    svc = MagicMock()
    svc.saved_searches.__getitem__.side_effect = KeyError("not found")
    mock_gc.return_value.service = svc

    yml = tmp_path / "rules.yml"
    yml.write_text(yaml.dump([{"name": "new_rule", "search": "index=x"}]))
    result = CliRunner().invoke(cli, ["rules", "import", "--path", str(yml)])
    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    assert "[DRY RUN]" in result.stderr
    assert "create: new_rule" in result.stderr
