import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]
VMLAB = ROOT / "installers" / "vmlab"


def run_bash(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_config_exposes_pinned_sse_and_lab_defaults(tmp_path: Path) -> None:
    result = run_bash(
        f"source {VMLAB / 'config.env'}; "
        "printf '%s\n' \"$SSE_TGZ\" \"$SSE_INDEX\" \"$SIEM_IP\" \"$SOAR_IP\" "
        "\"$SSE_DATA_DIR\" \"$SSE_HEC_TOKEN_FILE\"",
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
    result = subprocess.run(
        [str(VMLAB / "check-lab.sh"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--only siem|soar|both" in result.stdout
