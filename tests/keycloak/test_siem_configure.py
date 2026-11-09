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
    write_executable(fake_bin / "curl", f'#!/bin/sh\ncat "{metadata}"\n')
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
