import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
VMLAB = ROOT / "installers" / "vmlab"


def run_bash(
    script: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(  # noqa: S603
        ["/usr/bin/bash", "-c", script],
        cwd=ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


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


def test_data_command_prepare_runs_the_transformer_dry_run(tmp_path: Path) -> None:
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
    result = subprocess.run(  # noqa: S603
        [
            str(VMLAB / "import-sse-data.sh"),
            "prepare",
            "--anchor",
            "2026-08-15T12:00:00Z",
            "--dry-run",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "INSTALLERS_DIR": str(tmp_path),
            "SSE_TGZ": package.name,
            "SSE_DATA_DIR": str(tmp_path / "prepared"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert '"dataset_count": 2' in result.stdout
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["reset", "--anchor", "2026-08-15T12:00:00Z"],
        ["import", "--clear-existing"],
    ],
)
def test_destructive_data_commands_reject_a_non_lab_index(
    arguments: list[str], tmp_path: Path
) -> None:
    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "import-sse-data.sh"), *arguments],
        cwd=ROOT,
        env={
            **os.environ,
            "SSE_INDEX": "main",
            "SSE_DATA_DIR": str(tmp_path),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "refusing cleanup outside sse_lab" in result.stderr


def test_import_skips_a_complete_indexed_batch(tmp_path: Path) -> None:
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
    prepared = tmp_path / "prepared"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(VMLAB / "prepare-sse-data.py"),
            "--package",
            str(package),
            "--output-dir",
            str(prepared),
            "--index",
            "sse_lab",
            "--anchor",
            "2026-08-15T12:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "scp", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "ssh",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *'sudo bash -s'*) cat >/dev/null; printf 'no' ;;\n"
        "esac\n"
        "exit 0\n",
    )
    write_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_CURL_LOG"\n'
        'case "$*" in\n'
        "  *services/collector/health*) printf '200' ;;\n"
        "  *'stats count by lab_batch_id'*) "
        "printf '%s\\n' "
        '\'{"preview":false,"result":{"lab_batch_id":"000001","count":"3"}}\' ;;\n'
        "  *'stats count'*) printf '%s\\n' "
        '\'{"preview":true,"result":{"count":"1"}}\' '
        '\'{"preview":false,"result":{"count":"3"}}\' ;;\n'
        "  *services/collector/event*) printf '%s' "
        '\'{"text":"Success","code":0}\' ;;\n'
        "esac\n",
    )
    key = tmp_path / "lab-key"
    key.write_text("test key")
    token = tmp_path / "hec-token"
    token.write_text("test-token")
    token.chmod(0o600)

    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "import-sse-data.sh"), "import"],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_CURL_LOG": str(curl_log),
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SIEM_IP": "192.0.2.10",
            "SPLUNK_ADMIN_PASSWORD": "test-password",
            "SSE_DATA_DIR": str(prepared),
            "SSE_HEC_TOKEN_FILE": str(token),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "batch 000001 already indexed; skipping" in result.stdout
    assert "services/collector/event" not in curl_log.read_text()


def test_clear_existing_stops_systemd_and_fails_before_import_on_error(
    tmp_path: Path,
) -> None:
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
    prepared = tmp_path / "prepared"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(VMLAB / "prepare-sse-data.py"),
            "--package",
            str(package),
            "--output-dir",
            str(prepared),
            "--index",
            "sse_lab",
            "--anchor",
            "2026-08-15T12:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh_log = tmp_path / "ssh.log"
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "scp", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "ssh",
        "#!/bin/sh\n"
        'printf \'%s\n\' "$*" >> "$FAKE_SSH_LOG"\n'
        'case "$*" in\n'
        "  *'sudo bash -s'*) cat >/dev/null; printf 'no' ;;\n"
        "esac\n"
        "exit 0\n",
    )
    write_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *:8000*) printf '303' ;;\n"
        "  *services/collector/health*) printf '200' ;;\n"
        "  *'stats count by lab_batch_id'*) : ;;\n"
        "  *'stats count'*) printf '%s\\n' '{\"result\":{\"count\":\"3\"}}' ;;\n"
        "  *services/collector/event*) printf '%s' "
        '\'{"text":"Success","code":0}\' ;;\n'
        "esac\n",
    )
    key = tmp_path / "lab-key"
    key.write_text("test key")
    token = tmp_path / "hec-token"
    token.write_text("test-token")
    token.chmod(0o600)

    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "import-sse-data.sh"), "import", "--clear-existing"],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_SSH_LOG": str(ssh_log),
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SIEM_IP": "192.0.2.10",
            "SPLUNK_ADMIN_PASSWORD": "test-password",
            "SSE_DATA_DIR": str(prepared),
            "SSE_HEC_TOKEN_FILE": str(token),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    clear_command = next(
        line for line in ssh_log.read_text().splitlines() if "clean eventdata" in line
    )
    assert "set -e" in clear_command
    assert "sudo systemctl stop Splunkd" in clear_command
    assert "/opt/splunk/bin/splunk stop" not in clear_command
    assert "clean eventdata -index 'sse_lab' -f" in clear_command


def test_splunk_install_skips_copy_when_pinned_version_is_ready(
    tmp_path: Path,
) -> None:
    rpm_name = "splunk-10.4.2-33c3bf42cd73.x86_64.rpm"
    (tmp_path / rpm_name).write_bytes(b"rpm")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    scp_log = tmp_path / "scp.log"
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "curl", "#!/bin/sh\nprintf '303'\n")
    write_executable(
        fake_bin / "scp",
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$FAKE_SCP_LOG"\n',
    )
    write_executable(
        fake_bin / "ssh",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *'rpm -q --qf'*) printf '10.4.2-33c3bf42cd73.x86_64\\n' ;;\n"
        "esac\n"
        "exit 0\n",
    )
    key = tmp_path / "lab-key"
    key.write_text("test key")

    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "install-splunk.sh"), "--ip", "192.0.2.10"],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_SCP_LOG": str(scp_log),
            "INSTALLERS_DIR": str(tmp_path),
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SPLUNK_RPM": rpm_name,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "already installed and running" in result.stdout
    assert not scp_log.exists()


def test_soar_install_changes_directory_after_switching_user(tmp_path: Path) -> None:
    tgz_name = "splunk_soar-unpriv-8.6.0.530-test-el9-x86_64.tgz"
    (tmp_path / tgz_name).write_bytes(b"tgz")
    vm_base = tmp_path / "vms"
    vm_dir = vm_base / "soar"
    vm_dir.mkdir(parents=True)
    (vm_dir / "soar.vmx").write_text("test vmx")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh_log = tmp_path / "ssh.log"
    installed = tmp_path / "soar-installed"
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "scp", "#!/bin/sh\nexit 0\n")
    write_executable(fake_bin / "curl", "#!/bin/sh\nprintf '200'\n")
    write_executable(fake_bin / "vmrun", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "ssh",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_SSH_LOG"\n'
        'case "$*" in\n'
        "  *'test -x /opt/phantom/bin/phsvc'*) "
        'test -f "$FAKE_SOAR_INSTALLED"; exit $? ;;\n'
        "  *'test -x /home/soar/splunk-soar/soar-install'*) exit 0 ;;\n"
        "  *'./soar-install'*) : > \"$FAKE_SOAR_INSTALLED\" ;;\n"
        "  *product_version*) "
        "test -f \"$FAKE_SOAR_INSTALLED\" && printf '8.6.0.530\\n' ;;\n"
        "esac\n"
        "exit 0\n",
    )
    key = tmp_path / "lab-key"
    key.write_text("test key")

    result = subprocess.run(  # noqa: S603
        [
            str(VMLAB / "install-soar.sh"),
            "--name",
            "soar",
            "--ip",
            "192.0.2.11",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_SOAR_INSTALLED": str(installed),
            "FAKE_SSH_LOG": str(ssh_log),
            "INSTALLERS_DIR": str(tmp_path),
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SOAR_TGZ": tgz_name,
            "VM_BASE_DIR": str(vm_base),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    install_command = next(
        line for line in ssh_log.read_text().splitlines() if "./soar-install" in line
    )
    assert "cd /home/soar/splunk-soar && sudo -u soar" not in install_command
    assert "sudo -u soar bash -c" in install_command


def test_build_refuses_an_existing_vm_without_stopping_it(tmp_path: Path) -> None:
    vm_base = tmp_path / "vms"
    vm_dir = vm_base / "siem"
    vm_dir.mkdir(parents=True)
    vmx = vm_dir / "siem.vmx"
    vmx.write_text("existing vm")
    (tmp_path / "rhel.iso").write_bytes(b"iso")
    key = tmp_path / "lab-key"
    key.write_text("test key")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    vmrun_log = tmp_path / "vmrun.log"
    write_executable(
        fake_bin / "vmrun",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_VMRUN_LOG"\n'
        'if [ "$1" = list ]; then '
        "printf 'Total running VMs: 1\\n%s\\n' \"$FAKE_VMX\"; fi\n",
    )

    result = subprocess.run(  # noqa: S603
        [
            str(VMLAB / "build-rhel-vm.sh"),
            "--name",
            "siem",
            "--ip",
            "192.0.2.10",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_VMRUN_LOG": str(vmrun_log),
            "FAKE_VMX": str(vmx),
            "INSTALLERS_DIR": str(tmp_path),
            "LAB_SSH_KEY": str(key),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "RHEL_ISO": "rhel.iso",
            "VM_BASE_DIR": str(vm_base),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "VM dir already exists" in result.stderr
    vmrun_calls = vmrun_log.read_text() if vmrun_log.exists() else ""
    assert " stop " not in f" {vmrun_calls} "


def test_provision_reuses_existing_vms_and_orders_stages(tmp_path: Path) -> None:
    scripts = tmp_path / "vmlab"
    scripts.mkdir()
    for name in ("provision-lab.sh", "lib.sh", "config.env"):
        shutil.copy2(VMLAB / name, scripts / name)
    stage_log = tmp_path / "stages.log"
    for name in (
        "check-lab.sh",
        "build-rhel-vm.sh",
        "install-splunk.sh",
        "install-sse.sh",
        "import-sse-data.sh",
        "install-soar.sh",
        "verify-lab.sh",
    ):
        write_executable(
            scripts / name,
            f"#!/bin/sh\nprintf '%s %s\\n' '{name}' \"$*\" >> \"$FAKE_STAGE_LOG\"\n",
        )
    vm_base = tmp_path / "vms"
    vmxs = []
    for name in ("siem", "soar"):
        vm_dir = vm_base / name
        vm_dir.mkdir(parents=True)
        vmx = vm_dir / f"{name}.vmx"
        vmx.write_text("existing vm")
        vmxs.append(vmx)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "nc", "#!/bin/sh\nexit 0\n")
    write_executable(
        fake_bin / "vmrun",
        "#!/bin/sh\n"
        'if [ "$1" = list ]; then\n'
        "  printf 'Total running VMs: 2\\n%s\\n%s\\n' "
        '"$FAKE_SIEM_VMX" "$FAKE_SOAR_VMX"\n'
        "fi\n",
    )

    result = subprocess.run(  # noqa: S603
        [str(scripts / "provision-lab.sh"), "--only", "both", "--skip-data"],
        env={
            **os.environ,
            "FAKE_SIEM_VMX": str(vmxs[0]),
            "FAKE_SOAR_VMX": str(vmxs[1]),
            "FAKE_STAGE_LOG": str(stage_log),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "VM_BASE_DIR": str(vm_base),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    stages = stage_log.read_text().splitlines()
    assert stages[0].startswith("check-lab.sh")
    assert not any(stage.startswith("build-rhel-vm.sh") for stage in stages)
    assert any(stage.startswith("install-splunk.sh") for stage in stages)
    assert any(stage.startswith("install-sse.sh") for stage in stages)
    assert any(stage.startswith("install-soar.sh") for stage in stages)
    assert not any(stage.startswith("import-sse-data.sh") for stage in stages)
    assert stages[-1].startswith("verify-lab.sh")


def test_verify_help_lists_role_and_data_selection() -> None:
    result = subprocess.run(  # noqa: S603
        [str(VMLAB / "verify-lab.sh"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--only siem|soar|both" in result.stdout
    assert "--skip-data" in result.stdout
