"""Offline SIEM SAML configuration rendering and metadata validation."""

import configparser
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.vmlab.script_helpers import ROOT, write_executable

KC = ROOT / "lab" / "keycloak"


@pytest.mark.parametrize("count", [0, 1, 2])
def test_siem_configure(tmp_path: Path, count: int) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    cert = "QUJD" * 40
    descriptor = (
        '<root xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        + (f"<ds:X509Certificate>\n{cert}\n</ds:X509Certificate>" * count)
        + "</root>"
    )
    metadata = tmp_path / "descriptor.xml"
    metadata.write_text(descriptor)
    write_executable(
        fake_bin / "curl",
        '#!/bin/sh\ncase "$*" in\n'
        "  */account/login*) echo '<input name=\"SAMLRequest\">' ;;\n"
        f'  *) cat "{metadata}" ;;\nesac\n',
    )
    write_executable(
        fake_bin / "scp",
        f'#!/bin/sh\nfor arg in "$@"; do\n'
        f'  case "$arg" in *:*) ;; *.conf|*.pem) cp "$arg" "{tmp_path}/" ;;\n'
        "  esac\ndone\n",
    )
    remote = tmp_path / "remote.sh"
    write_executable(fake_bin / "ssh", f'#!/bin/sh\ncat > "{remote}"\n')
    result = subprocess.run(  # noqa: S603
        [str(KC / "siem-configure.sh")],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "SIEM_HOST": "192.0.2.10",
            "SIEM_WEB_PORT": "9000",
            "REALM": "testrealm",
            "KEYCLOAK_HOST": "192.0.2.1",
            "KEYCLOAK_PORT": "8081",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if count != 1:
        assert result.returncode != 0
        assert "exactly one" in result.stdout + result.stderr
        assert not remote.exists()
        return
    assert result.returncode == 0, result.stderr
    conf_text = (tmp_path / "authentication.conf").read_text()
    conf = configparser.ConfigParser()
    conf.read_string(conf_text)
    assert conf["authentication"]["authType"] == "SAML"
    assert conf["roleMap_SAML"]["admin"] == "splunk-admin"
    assert conf["authenticationResponseAttrMap_SAML"]["role"] == "Role"
    assert dict(conf["saml"]) == {
        "allowpartialsignatures": "false",
        "entityid": "splunk-siem",
        "fqdn": "http://192.0.2.10",
        "idpcertpath": "keycloak-testrealm.pem",
        "idpssourl": "http://192.0.2.1:8081/realms/testrealm/protocol/saml",
        "inboundsignaturealgorithm": "RSA-SHA256;RSA-SHA384;RSA-SHA512",
        "issuerid": "http://192.0.2.1:8081/realms/testrealm",
        "nameidformat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "redirectport": "9000",
        "replicatecertificates": "false",
        "signauthnrequest": "false",
        "signedassertion": "true",
        "ssobinding": "HTTPPost",
    }
    pem = (tmp_path / "keycloak-testrealm.pem").read_text().splitlines()
    assert pem[0] == "-----BEGIN CERTIFICATE-----"
    assert pem[-1] == "-----END CERTIFICATE-----"
    assert "".join(pem[1:-1]) == cert
    assert all(len(line) == 64 for line in pem[1:-2])
    assert not re.search(r"/(?:home|Users)/[^/\s]+", conf_text + "\n".join(pem))
    assert "SIEM SAML is configured" in result.stdout


def run_with_remote(
    tmp_path: Path,
    *,
    systemd: bool = True,
    page: str = '<form><input name="SAMLRequest" value="encoded"></form>',
    restart_status: int = 0,
    web_status: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Execute the remote block with service and network commands stubbed."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (tmp_path / "page.html").write_text(page)
    write_executable(
        fake_bin / "curl",
        '#!/bin/sh\ncase "$*" in\n'
        '  */descriptor) echo \'<root xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        "<ds:X509Certificate>QUJD</ds:X509Certificate></root>' ;;\n"
        '  */account/login) echo login >> "$CALLS"; '
        '[ "$WEB_STATUS" = 0 ] || exit "$WEB_STATUS"; '
        'cat "$HOME/page.html" ;;\n'
        "  *) exit 99 ;;\nesac\n",
    )
    for command in ("scp", "install", "sleep"):
        write_executable(fake_bin / command, "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "ssh",
        '#!/bin/sh\ncat > "$HOME/remote.sh"\n'
        'bash "$HOME/remote.sh" "$SPLUNK_HOME" "$HOME/staging" testrealm\n',
    )
    write_executable(
        fake_bin / "sudo",
        '#!/bin/sh\n[ "$1 $2 $3" = "-n -u splunk" ] || exit 99\nshift 3\nexec "$@"\n',
    )
    write_executable(
        fake_bin / "systemctl",
        '#!/bin/sh\necho "systemctl $*" >> "$CALLS"\n'
        'case "$*" in\n'
        '  "cat Splunkd") exit "$UNIT_STATUS" ;;\n'
        '  "restart Splunkd") exit "$RESTART_STATUS" ;;\n'
        "  *) exit 99 ;;\nesac\n",
    )
    write_executable(
        fake_bin / "splunk",
        '#!/bin/sh\necho "splunk $*" >> "$CALLS"\n'
        'case "$*" in\n'
        '  "btool check") exit 0 ;;\n'
        '  "restart --answer-yes --no-prompt") exit "$RESTART_STATUS" ;;\n'
        "  *) exit 99 ;;\nesac\n",
    )
    return subprocess.run(  # noqa: S603
        [str(KC / "siem-configure.sh")],
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "SPLUNK_HOME": str(tmp_path),
            "SIEM_HOST": "192.0.2.10",
            "REALM": "testrealm",
            "KEYCLOAK_HOST": "192.0.2.1",
            "KEYCLOAK_PORT": "8081",
            "CALLS": str(tmp_path / "calls"),
            "UNIT_STATUS": "0" if systemd else "1",
            "RESTART_STATUS": str(restart_status),
            "WEB_STATUS": str(web_status),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


@pytest.mark.parametrize("systemd", [True, False])
def test_restart_service(tmp_path: Path, systemd: bool) -> None:
    result = run_with_remote(tmp_path, systemd=systemd)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls").read_text().splitlines()
    assert calls == [
        "splunk btool check",
        "systemctl cat Splunkd",
        "systemctl restart Splunkd"
        if systemd
        else "splunk restart --answer-yes --no-prompt",
        "login",
    ]


@pytest.mark.parametrize("systemd", [True, False])
def test_restart_failure_stops_configuration(tmp_path: Path, systemd: bool) -> None:
    result = run_with_remote(tmp_path, systemd=systemd, restart_status=7)
    assert result.returncode != 0
    assert "login" not in (tmp_path / "calls").read_text().splitlines()
    assert "SIEM SAML is configured" not in result.stdout


@pytest.mark.parametrize(
    "page",
    [
        '<form><input name="SAMLRequest" value="encoded"></form>',
        '<form method="post" action="http://192.0.2.1:8081/realms/'
        'testrealm/protocol/saml?client_id=splunk-siem"></form>',
    ],
)
def test_readiness_accepts_saml_form(tmp_path: Path, page: str) -> None:
    result = run_with_remote(tmp_path, page=page)
    assert result.returncode == 0, result.stderr
    assert "SIEM SAML is configured" in result.stdout


@pytest.mark.parametrize("web_status", [0, 7])
def test_readiness_requires_saml(tmp_path: Path, web_status: int) -> None:
    result = run_with_remote(tmp_path, page="<html>Login</html>", web_status=web_status)
    assert result.returncode != 0
    message = (
        "Splunk Web is up but SAML is not active (restart failed?)"
        if web_status == 0
        else "Splunk Web did not become ready"
    )
    assert message in result.stderr
    assert "SIEM SAML is configured" not in result.stdout
    assert (tmp_path / "calls").read_text().splitlines().count("login") == 120
