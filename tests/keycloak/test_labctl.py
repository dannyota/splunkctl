"""Tests for the Keycloak labctl.sh dispatcher."""

import os
import shutil
import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import ROOT, write_executable

KC = ROOT / "lab" / "keycloak"


def _run_labctl(
    subcmd: str, tmp_path: Path, podman_body: str
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "podman", podman_body)
    write_executable(fake_bin / "podman-compose", "#!/bin/sh\nexit 0\n")
    # status probes the health URL; report "down" so the test is hermetic.
    write_executable(fake_bin / "curl", "#!/bin/sh\nprintf '000'\n")
    return subprocess.run(  # noqa: S603
        [str(KC / "labctl.sh"), subcmd],
        cwd=ROOT,
        env={"PATH": f"{fake_bin}:{os.environ['PATH']}", "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
    )


def test_status_reports_down_when_not_running(tmp_path: Path) -> None:
    result = _run_labctl(
        "status",
        tmp_path,
        "#!/bin/sh\nprintf '[]\\n'\n",
    )
    assert result.returncode == 0, result.stderr
    assert "not running" in result.stdout


def test_start_requires_podman(tmp_path: Path) -> None:
    # labctl.sh needs bash (via the `env` shebang) and `dirname` to source
    # lib.sh before it can check for podman. Put those on a minimal PATH and
    # leave podman out, so the `require_podman` guard fires.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "bash").symlink_to(Path(shutil.which("bash") or "/bin/bash"))
    (fake_bin / "dirname").symlink_to(
        Path(shutil.which("dirname") or "/usr/bin/dirname")
    )
    result = subprocess.run(  # noqa: S603
        [str(KC / "labctl.sh"), "start"],
        cwd=ROOT,
        env={"PATH": str(fake_bin), "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "required command not found: podman" in result.stderr


def test_configure_renders_and_imports_realm(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir(exist_ok=True)
    fake_bin = tmp_path / "bin"
    (fake_bin / "podman").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "podman-compose").write_text("#!/bin/sh\nexit 0\n")
    log_file = tmp_path / "curl.log"
    write_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_CURL_LOG"\n'
        'case "$*" in\n'
        '  *openid-connect/token*) printf \'{"access_token":"tok"}\' ;;\n'
        "  *) printf '201' ;;\n"
        "esac\n",
    )
    result = subprocess.run(  # noqa: S603
        [str(KC / "labctl.sh"), "configure"],
        cwd=ROOT,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "FAKE_CURL_LOG": str(log_file),
            "KEYCLOAK_ADMIN_PASSWORD": "pw",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log_file.read_text()
    assert "realms/master/protocol/openid-connect/token" in calls
    assert "admin/realms" in calls


def test_verify_fails_when_health_is_down(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "podman", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "podman-compose", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "curl", "#!/bin/sh\nprintf '000'\n")
    result = subprocess.run(  # noqa: S603
        [str(KC / "labctl.sh"), "verify"],
        cwd=ROOT,
        env={"PATH": f"{fake_bin}:{os.environ['PATH']}", "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "health" in result.stderr
