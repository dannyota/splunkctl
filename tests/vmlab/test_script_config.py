import os
import re
import shutil
import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import (
    ROOT,
    VMLAB,
    run_bash,
    write_executable,
)


def test_config_exposes_pinned_sse_and_lab_defaults(tmp_path: Path) -> None:
    result = run_bash(
        f"source {VMLAB / 'config.env'}; "
        'printf \'%s\n\' "$SSE_TGZ" "$SSE_INDEX" "$SIEM_IP" "$SOAR_IP" '
        '"$SSE_DATA_DIR" "$SSE_HEC_TOKEN_FILE"',
        env={"HOME": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "splunk-security-essentials_383.tgz",
        "sse_lab",
        "100.65.1.10",
        "100.65.1.11",
        f"{tmp_path}/vmware/sse-data",
        f"{tmp_path}/vmware/.sse_hec_token",
    ]


def test_reset_guard_rejects_an_index_outside_the_lab() -> None:
    result = run_bash(
        f"source {VMLAB / 'lib.sh'}; require_sse_lab_index",
        env={"SSE_INDEX": "main"},
    )

    assert result.returncode != 0
    assert "refusing cleanup outside sse_lab" in result.stderr


def test_reset_guard_accepts_the_lab_index() -> None:
    result = run_bash(f"source {VMLAB / 'lib.sh'}; require_sse_lab_index")

    assert result.returncode == 0, result.stderr


def test_vmx_path_uses_the_configured_base_directory(tmp_path: Path) -> None:
    result = run_bash(
        f"source {VMLAB / 'lib.sh'}; vmx_path siem",
        env={"VM_BASE_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{tmp_path}/siem/siem.vmx"


def test_installer_directory_can_point_at_shared_ignored_artifacts(
    tmp_path: Path,
) -> None:
    result = run_bash(
        f"source {VMLAB / 'lib.sh'}; printf '%s' \"$INSTALLERS_DIR\"",
        env={"INSTALLERS_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == str(tmp_path)


def test_preflight_help_lists_role_selection() -> None:
    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "check-lab.sh"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--only siem|soar|both" in result.stdout


def test_preflight_does_not_create_vm_base_dir(tmp_path: Path) -> None:
    base = tmp_path / "missing" / "vmware"
    stubs = tmp_path / "bin"
    stubs.mkdir()
    # Unreachable lab IPs make BSD nc wait for the connect timeout.
    write_executable(stubs / "nc", "#!/usr/bin/env bash\nexit 1\n")
    result = run_bash(
        f"{VMLAB / 'check-lab.sh'} --only siem",
        env={
            "VM_BASE_DIR": str(base),
            "INSTALLERS_DIR": str(tmp_path),
            "PATH": f"{stubs}:{os.environ['PATH']}",
        },
    )

    # Preflight fails here (no VMware, no installers); it must still be
    # read-only and report free space from the nearest existing parent.
    assert not (tmp_path / "missing").exists()
    assert f"free space under {tmp_path}:" in result.stdout + result.stderr


def test_install_sse_help_names_the_siem_address_option() -> None:
    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "install-sse.sh"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--ip ADDRESS" in result.stdout


def test_install_sse_skips_an_existing_matching_app(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "sse-mini"
    package = tmp_path / "sse.tgz"
    subprocess.run(  # noqa: S603
        [
            "/usr/bin/tar",
            "-czf",
            str(package),
            "-C",
            str(fixture),
            "Splunk_Security_Essentials",
        ],
        check=True,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "ssh",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *default/app.conf*) printf '3.8.3\\n' ;;\n"
        "esac\n"
        "exit 0\n",
    )
    key = tmp_path / "lab-key"
    key.write_text("test key")

    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "install-sse.sh"), "--ip", "192.0.2.10"],
        cwd=ROOT,
        env={
            **os.environ,
            "INSTALLERS_DIR": str(tmp_path),
            "SSE_TGZ": package.name,
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SSE 3.8.3 is already installed" in result.stdout


def _sandboxed_vmlab(tmp_path: Path) -> Path:
    """Copy installers/vmlab with every stage script stubbed to fail loudly.

    A guard regression must fail the test, never provision a real VM.
    """
    lab = tmp_path / "vmlab"
    shutil.copytree(VMLAB, lab, ignore=shutil.ignore_patterns("config.local.env"))
    for name in (
        "check-lab.sh",
        "build-rhel-vm.sh",
        "install-splunk.sh",
        "install-soar.sh",
        "install-sse.sh",
        "import-sse-data.sh",
    ):
        (lab / name).write_text("#!/usr/bin/env bash\necho STAGE-RAN >&2\nexit 99\n")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for tool in ("vmrun", "vmware", "ssh", "ssh-keygen", "scp"):
        stub = stubs / tool
        stub.write_text("#!/usr/bin/env bash\necho TOOL-RAN >&2\nexit 99\n")
        stub.chmod(0o755)
    return lab


def test_provision_rejects_placeholder_password(tmp_path: Path) -> None:
    lab = _sandboxed_vmlab(tmp_path)
    result = run_bash(
        f"{lab / 'provision-lab.sh'}",
        env={
            "LAB_PASSWORD": "changeme",
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path / 'bin'}:{os.environ.get('PATH', '')}",
        },
    )
    assert result.returncode == 1, result.stderr
    assert "set LAB_PASSWORD in config.env before provisioning" in result.stderr
    assert "STAGE-RAN" not in result.stderr
    assert "TOOL-RAN" not in result.stderr
    assert not (tmp_path / "vmware").exists()


def test_provision_guard_ignores_local_env_overrides(tmp_path: Path) -> None:
    lab = _sandboxed_vmlab(tmp_path)
    (lab / "config.local.env").write_text("LAB_PASSWORD=real-secret\n")
    result = run_bash(
        f"{lab / 'provision-lab.sh'}",
        env={
            "LAB_PASSWORD": "changeme",
            "HOME": str(tmp_path),
            "PATH": f"{tmp_path / 'bin'}:{os.environ.get('PATH', '')}",
        },
    )
    assert result.returncode == 1, result.stderr
    assert "set LAB_PASSWORD in config.env before provisioning" in result.stderr


def test_reusable_lab_files_have_no_maintainer_defaults() -> None:
    password_pattern = re.compile(r"Splunk@\d{4}")
    for name in (
        "installers/vmlab/README.md",
        "lab/keycloak/README.md",
        "lab/keycloak/.env.example",
        "installers/vmlab/config.env",
        "docs/guides/keycloak-lab.md",
    ):
        content = (ROOT / name).read_text()
        password_found = password_pattern.search(content) is not None
        assert not password_found, (name, "Splunk@<year> password")
        for forbidden in (
            "/home/danny",
            "/Users/danny",
            "Documents/ISOs",
            "Asia/Ho_Chi_Minh",
        ):
            assert forbidden not in content, (name, forbidden)
