import hashlib
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.vmlab.script_helpers import VMLAB, run_bash, write_executable


def setup_fetch(tmp_path: Path) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "curl",
        f"#!{sys.executable}\n"
        "import json, os, pathlib, signal, sys, time\n"
        "url = sys.argv[2]\n"
        "with open(os.environ['CURL_LOG'], 'a') as log: log.write(url + '\\n')\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "if 'CURL_BARRIER' in os.environ:\n"
        "    barrier = pathlib.Path(os.environ['CURL_BARRIER'])\n"
        "    (barrier / str(os.getpid())).write_text(str(out))\n"
        "    deadline = time.monotonic() + 5\n"
        "    while len(list(barrier.iterdir())) < 2:\n"
        "        if time.monotonic() > deadline: sys.exit(1)\n"
        "        time.sleep(0.01)\n"
        "out.write_text(json.loads(os.environ['CURL_PAYLOADS'])[url])\n"
        "if 'CURL_SIGNAL' in os.environ:\n"
        "    os.kill(os.getppid(), getattr(signal, os.environ['CURL_SIGNAL']))\n"
        "sys.exit(int(os.environ.get('CURL_EXIT', '0')))\n",
    )
    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "CURL_LOG": str(tmp_path / "curl.log"),
        "INSTALLERS_DIR": str(tmp_path),
    }
    payloads = {}
    for name, algorithm in (
        ("RHEL_ISO", "sha256"),
        ("SSE_TGZ", "sha256"),
        ("SPLUNK_RPM", "sha512"),
        ("SOAR_TGZ", "sha512"),
    ):
        env[name] = name.lower()
        payload = f"payload for {name}"
        if name in ("SPLUNK_RPM", "SOAR_TGZ"):
            url = f"https://example.test/{name}"
            env[f"{name}_URL"] = url
            payloads[url] = payload
        env[f"{name}_{algorithm.upper()}"] = hashlib.new(
            algorithm, payload.encode()
        ).hexdigest()
        (tmp_path / env[name]).write_text(payload)
    env["CURL_PAYLOADS"] = json.dumps(payloads)
    return env


@pytest.mark.parametrize(
    "role,artifact", [("siem", "SPLUNK_RPM"), ("soar", "SOAR_TGZ")]
)
def test_downloads_and_verifies_missing_installer(
    tmp_path: Path, role: str, artifact: str
) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env[artifact]
    dest.unlink()
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only {role}", env=env)
    assert result.returncode == 0, result.stderr
    assert dest.read_text() == f"payload for {artifact}"
    assert Path(env["CURL_LOG"]).read_text().splitlines() == [env[f"{artifact}_URL"]]
    assert not list(tmp_path.glob(f".{dest.name}.*"))
    assert "OK" in result.stdout


def test_bad_download_is_removed(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    env["SPLUNK_RPM_SHA512"] = "0" * 128
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode != 0
    assert "mismatch" in result.stderr
    assert not dest.exists()
    assert not list(tmp_path.glob(f".{dest.name}.*"))


def test_existing_installers_are_never_downloaded(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'}", env=env)
    assert result.returncode == 0, result.stderr
    assert not Path(env["CURL_LOG"]).exists()


def test_check_never_downloads(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    (tmp_path / env["SOAR_TGZ"]).unlink()
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --check", env=env)
    assert result.returncode != 0
    assert not Path(env["CURL_LOG"]).exists()


def test_missing_sse_reports_download_guidance(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    (tmp_path / env["SSE_TGZ"]).unlink()
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode != 0
    assert "Splunkbase" in result.stderr
    assert "3435" in result.stderr
    assert "3.8.3" in result.stderr


def test_existing_bad_file_is_preserved(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["RHEL_ISO"]
    dest.write_bytes(b"bad")
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'}", env=env)
    assert result.returncode != 0
    assert dest.read_bytes() == b"bad"
    assert not Path(env["CURL_LOG"]).exists()


def test_check_uses_shasum_without_gnu_checksum_commands(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    minimal = tmp_path / "minimal"
    minimal.mkdir()
    for command in ("bash", "dirname", "shasum"):
        executable = shutil.which(command)
        assert executable is not None
        (minimal / command).symlink_to(executable)
    env["PATH"] = str(minimal)
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --check", env=env)
    assert result.returncode == 0, result.stderr
    assert "4 OK, 0 missing or failed" in result.stdout


@pytest.mark.parametrize("role", ["siem", "soar"])
@pytest.mark.parametrize("unselected_state", ["missing", "corrupt"])
def test_only_ignores_unselected_artifacts(
    tmp_path: Path, role: str, unselected_state: str
) -> None:
    env = setup_fetch(tmp_path)
    unselected = ["SOAR_TGZ"] if role == "siem" else ["SPLUNK_RPM", "SSE_TGZ"]
    for artifact in unselected:
        dest = tmp_path / env[artifact]
        if unselected_state == "missing":
            dest.unlink()
        else:
            dest.write_text("corrupt")
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only {role}", env=env)
    assert result.returncode == 0, result.stderr
    for artifact in unselected:
        assert env[artifact] not in result.stdout + result.stderr


def test_coordinated_installer_overrides(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    env.update(
        SPLUNK_RPM="custom.rpm",
        SPLUNK_RPM_URL="https://example.test/custom.rpm",
        SPLUNK_RPM_SHA512=hashlib.sha512(b"custom payload").hexdigest(),
        CURL_PAYLOADS=json.dumps({"https://example.test/custom.rpm": "custom payload"}),
    )
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "custom.rpm").read_text() == "custom payload"
    assert Path(env["CURL_LOG"]).read_text().splitlines() == [env["SPLUNK_RPM_URL"]]


def test_leftover_partial_does_not_block_retry(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    partial = Path(f"{dest}.part")
    partial.write_text("old partial")
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode == 0, result.stderr
    assert dest.read_text() == "payload for SPLUNK_RPM"
    assert partial.read_text() == "old partial"
    assert not list(tmp_path.glob(f".{dest.name}.*"))


def test_destination_appears_at_publication(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    real_ln = shutil.which("ln")
    assert real_ln is not None
    write_executable(
        tmp_path / "bin" / "ln",
        f"#!{sys.executable}\n"
        "import pathlib, subprocess, sys\n"
        "pathlib.Path(sys.argv[2]).write_text('appeared')\n"
        f"sys.exit(subprocess.call([{real_ln!r}, *sys.argv[1:]]))\n",
    )
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode != 0
    assert "destination appeared during download (left unchanged)" in result.stderr
    assert dest.read_text() == "appeared"
    assert "2 OK, 1 missing or failed" in result.stdout
    assert not list(tmp_path.glob(f".{dest.name}.*"))


def test_failed_download_removes_temporary_file(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    env["CURL_EXIT"] = "22"
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode != 0
    assert "download failed" in result.stderr
    assert not dest.exists()
    assert not list(tmp_path.glob(f".{dest.name}.*"))


@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
def test_interrupted_download_removes_temporary_file(
    tmp_path: Path, signal_name: str
) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    env["CURL_SIGNAL"] = signal_name
    result = run_bash(f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env)
    assert result.returncode != 0
    assert not dest.exists()
    assert not list(tmp_path.glob(f".{dest.name}.*"))


def test_concurrent_downloads_reserve_separate_files(tmp_path: Path) -> None:
    env = setup_fetch(tmp_path)
    dest = tmp_path / env["SPLUNK_RPM"]
    dest.unlink()
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    env["CURL_BARRIER"] = str(barrier)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: run_bash(
                    f"{VMLAB / 'fetch-installers.sh'} --only siem", env=env
                ),
                range(2),
            )
        )
    assert sorted(result.returncode for result in results) == [0, 1]
    assert len({marker.read_text() for marker in barrier.iterdir()}) == 2
    assert dest.read_text() == "payload for SPLUNK_RPM"
    assert not list(tmp_path.glob(f".{dest.name}.*"))
    assert any("destination appeared during download" in r.stderr for r in results)
