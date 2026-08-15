"""Tests for the Keycloak lab config and shared library."""

import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import ROOT, run_bash

KC = ROOT / "lab" / "keycloak"


def test_env_example_exposes_defaults(tmp_path: Path) -> None:
    result = run_bash(
        f"source {KC / '.env.example'}; "
        'printf \'%s\\n\' "$KEYCLOAK_HOST" "$KEYCLOAK_PORT" "$REALM" "$SIEM_ACS" "$SOAR_ACS"'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "100.65.1.1",
        "8080",
        "splunklab",
        "http://100.65.1.10:8000/en-US/app/launcher/home",
        "https://100.65.1.11:8443",
    ]


def test_render_substitutes_tokens(tmp_path: Path) -> None:
    tmpl = tmp_path / "t.json"
    tmpl.write_text('{"acs": "@@SIEM_ACS@@"}')
    result = run_bash(
        f"source {KC / 'lib.sh'}; render {tmpl} 'SIEM_ACS=http://x/y'",
        env={"HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"acs": "http://x/y"}'
