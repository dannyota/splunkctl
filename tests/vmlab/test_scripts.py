import os
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
        '\'{"result":{"lab_batch_id":"000001","count":"3"}}\' ;;\n'
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
