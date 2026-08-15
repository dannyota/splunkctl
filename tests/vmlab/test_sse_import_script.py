import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.vmlab.script_helpers import ROOT, VMLAB, write_executable


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
