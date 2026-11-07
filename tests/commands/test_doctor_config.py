"""Invalid config files fail doctor before network access."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli


@pytest.mark.parametrize("contents", ["[broken", "- item\n", "42\n", "null\n"])
def test_doctor_invalid_config(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(contents)
    with patch("splunkctl.commands.doctor.get_client") as client:
        result = CliRunner().invoke(cli, ["--json", "--config", str(path), "doctor"])
    assert result.exit_code == 1
    client.assert_not_called()
    (row,) = json.loads(result.stdout)
    assert row["check"] == "Config"
    assert row["status"] == "FAIL"
    assert row["hint"] == "Fix or remove the file, or pass --config"
    assert str(path) in row["detail"]
    if contents != "[broken":
        assert row["detail"] == f"{path} is not a YAML mapping"
    assert "FAIL  Config" in result.stderr


def test_doctor_unreadable_config(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("profiles: {}\n")
    with (
        patch(
            "splunkctl.config._read_unchecked",
            side_effect=PermissionError("permission denied"),
        ),
        patch("splunkctl.commands.doctor.get_client") as client,
    ):
        result = CliRunner().invoke(cli, ["--json", "--config", str(path), "doctor"])
    assert result.exit_code == 1
    client.assert_not_called()
    assert json.loads(result.stdout) == [
        {
            "check": "Config",
            "status": "FAIL",
            "detail": "permission denied",
            "hint": "Fix or remove the file, or pass --config",
        }
    ]
