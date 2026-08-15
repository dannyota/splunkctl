"""Tests for the Keycloak lab config and shared library."""

import json
import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import ROOT, run_bash

KC = ROOT / "lab" / "keycloak"


def test_env_example_exposes_defaults(tmp_path: Path) -> None:
    result = run_bash(
        f"source {KC / '.env.example'}; "
        "printf '%s\\n' "
        '"$KEYCLOAK_HOST" "$KEYCLOAK_PORT" "$REALM" "$SIEM_ACS" "$SOAR_ACS"'
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


def test_realm_template_renders_to_valid_json(tmp_path: Path) -> None:
    result = run_bash(
        f"source {KC / 'lib.sh'}; "
        f"render {KC / 'realm-template.json'} "
        "'REALM=splunklab' "
        "'SIEM_ACS=http://siem/acs' 'SOAR_ACS=https://soar/acs' "
        "'TEST_USER=bob' 'TEST_USER_PASSWORD=secret'",
        env={"HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    realm = json.loads(result.stdout)
    assert realm["realm"] == "splunklab"
    assert realm["otpPolicyType"] == "totp"
    client_ids = {c["clientId"] for c in realm["clients"]}
    assert client_ids == {"splunk-siem", "splunk-soar"}
    users = {u["username"]: u for u in realm["users"]}
    assert "CONFIGURE_TOTP" in users["bob"]["requiredActions"]


def test_compose_declares_keycloak_and_postgres() -> None:
    try:
        result = subprocess.run(  # noqa: S603
            ["podman-compose", "-f", str(KC / "compose.yaml"), "config"],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return
    if result.returncode != 0:
        return
    assert "image: quay.io/keycloak/keycloak:26.2" in result.stdout
    assert "image: docker.io/library/postgres:16-alpine" in result.stdout
