import os
import shutil
import subprocess
from pathlib import Path

from tests.vmlab.script_helpers import ROOT, VMLAB, write_executable


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
