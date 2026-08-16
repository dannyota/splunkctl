"""Tests for the SOAR SAML config script."""

import json
import os
import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import ROOT, write_executable

KC = ROOT / "lab" / "keycloak"

IDP_METADATA = (
    '<md:EntityDescriptor entityID="http://idp/realms/splunklab"></md:EntityDescriptor>'
)
SOAR_METADATA = '<EntityDescriptor entityID="splunk-soar"></EntityDescriptor>'


def test_soar_configure_builds_and_writes_auth(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'case "$*" in\n'
        f"  *descriptor*) printf '%s' '{IDP_METADATA}' ;;\n"
        f"  *saml2/metadata*) printf '%s' '{SOAR_METADATA}' ;;\n"
        "  *) printf '' ;;\n"
        "esac\n",
    )
    capture = tmp_path / "soar_auth.json"
    write_executable(
        fake_bin / "scp",
        f'''#!/bin/sh
src=""
for a in "$@"; do
  case "$a" in
    -*) ;;
    *:*) ;;
    *) src="$a" ;;
  esac
done
cp "$src" "{capture}"
''',
    )
    write_executable(fake_bin / "ssh", "#!/bin/sh\nexit 0\n")

    result = subprocess.run(  # noqa: S603
        [str(KC / "soar-configure.sh")],
        cwd=ROOT,
        env={"PATH": f"{fake_bin}:{os.environ['PATH']}", "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    auth = json.loads(capture.read_text())
    assert auth["saml2"]["enabled"] is True
    assert auth["ldap"] == {"enabled": False, "providers": []}
    provider = auth["saml2"]["providers"][0]
    assert provider["name"] == "keycloak"
    assert provider["entityid"] == "splunk-soar"
    assert provider["issuer_id"] == "http://100.65.1.1:8080/realms/splunklab"
    assert provider["metadata_xml"] == IDP_METADATA
    assert provider["create_unknown_user"] is True
    assert provider["group_key"] == "Role"
    assert provider["group_role_mappings"] == [
        {"group": "splunk-admin", "role": 1},
        {"group": "soar-admin", "role": 1},
    ]
