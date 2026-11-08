"""Offline SOAR runner selection, licensing gate, and shared cleanup mechanics."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("live smoke script tests require bash on PATH", allow_module_level=True)

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts/live-smoke-soar.sh"
LIBRARY = ROOT / "scripts/live-smoke-lib.sh"
STUB = r"""
import json, os, sys
from pathlib import Path
args = [a for a in sys.argv[1:] if a not in ('--json', '--yes')]
with Path(os.environ['SMOKE_CALLS']).open('a') as handle:
    handle.write(json.dumps(args) + '\n')
if args[:3] == ['soar', 'playbooks', 'list'] and os.environ.get('SMOKE_ACTIVE'):
    print('[{"id":77,"name":"existing","labels":["events"],"active":true}]')
    sys.exit(0)
if args[:3] == ['soar', 'playbooks', 'list'] and os.environ.get('SMOKE_LIST_FAIL'):
    print('{"error":{"kind":"http","message":"no playbook data list"}}')
    sys.exit(1)
if args == ['failing-step']:
    sys.exit(1)
if args[:1] == ['cleanup']:
    sys.exit(2 if args[1] == os.environ.get('SMOKE_CLEANUP_FAIL') else 0)
if args[:3] == ['soar', 'users', 'list']:
    users = ('[{}]' if os.environ.get('SMOKE_BAD_USER')
             else '[{"id":1,"username":"admin"}]')
    print('[]' if '--type' in args else users)
elif args[:3] == ['soar', 'users', 'get']:
    print('{"id":1,"username":"admin"}')
elif args[:3] == ['soar', 'roles', 'list']:
    print('[{"id":1,"name":"admin"}]')
elif args[:3] == ['soar', 'roles', 'get']:
    print('{"id":1,"name":"admin"}')
else:
    print('[]')
"""


def stub_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    binary = tmp_path / "splunkctl-stub"
    binary.write_text(f"#!{sys.executable}\n" + STUB)
    binary.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    env = {
        **os.environ,
        "SPLUNKCTL": str(binary),
        "LIVE_PYTHON": sys.executable,
        "TMPDIR": str(tmp_path),
        "SMOKE_CALLS": str(calls),
        "LIVE_ONLY": "",
        "LIVE_SKIP": "",
    }
    for key in (
        "LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS",
        "LIVE_SOAR_ACTIONS",
        "LIVE_SOAR_ACTION_ASSET",
        "LIVE_SOAR_ACTION",
        "LIVE_SOAR_ACTION_PARAMS",
    ):
        env.pop(key, None)
    return env, calls


def recorded_calls(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize("skip", ["", "90-users-roles"])
def test_soar_group_selection(tmp_path: Path, skip: str) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(LIVE_ONLY="90-users-roles", LIVE_SKIP=skip)
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: 0 failure(s)" in result.stdout
    assert "SKIPPED 10-meta: not in LIVE_ONLY" in result.stdout
    if skip:
        assert "SKIPPED 90-users-roles: LIVE_SKIP" in result.stdout
        assert not calls.exists()
    else:
        actual = recorded_calls(calls)
        assert ["soar", "users", "list"] in actual
        assert ["soar", "roles", "list"] in actual
        assert all(
            call[:2] in (["soar", "users"], ["soar", "roles"]) for call in actual
        )


def test_soar_actions_are_off_by_default(tmp_path: Path) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(
        LIVE_ONLY="70-assets-actions",
        LIVE_SOAR_ACTION_ASSET="existing-asset",
        LIVE_SOAR_ACTION="lookup domain",
    )
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    actual = recorded_calls(calls)
    assert ["soar", "actions", "list"] in actual
    assert not any(call[:3] == ["soar", "actions", "run"] for call in actual)
    assert not any(call[:3] == ["soar", "assets", "test"] for call in actual)
    assert "SKIPPED" in result.stdout


@pytest.mark.parametrize("failed_cleanup", ["", "second"])
def test_cleanup_reverses_and_survives_failures(
    tmp_path: Path, failed_cleanup: str
) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(SMOKE_LIBRARY=str(LIBRARY), SMOKE_CLEANUP_FAIL=failed_cleanup)
    harness = r"""
set -uo pipefail
S=$SPLUNKCTL PY=$LIVE_PYTHON
T=$(mktemp -d "$TMPDIR/sc-live.XXXXXX")
N=sc_live_test
fail=0
: > "$T/cleanup.sh"
. "$SMOKE_LIBRARY"
cleanup() { "$S" cleanup "$1"; }
defer cleanup first
defer cleanup second
defer cleanup third
expect_ok "$S" failing-step
"""
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", harness],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert recorded_calls(calls) == [
        ["failing-step"],
        ["cleanup", "third"],
        ["cleanup", "second"],
        ["cleanup", "first"],
    ]
    count = 2 if failed_cleanup else 1
    assert f"RESULT: {count} failure(s)" in result.stdout
    retained = list(tmp_path.glob("sc-live.*"))
    assert bool(retained) == bool(failed_cleanup)
    if failed_cleanup:
        assert len(retained) == 1
        assert str(retained[0]) in result.stdout
        assert "Remaining commands:" in result.stdout
        assert (retained[0] / "remaining.sh").read_text().strip() == "cleanup second"


def test_json_extraction_failure_counts(tmp_path: Path) -> None:
    env, _ = stub_environment(tmp_path)
    env.update(LIVE_ONLY="90-users-roles", SMOKE_BAD_USER="1")
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL JSON extraction" in result.stdout
    assert "RESULT: 1 failure(s)" in result.stdout


def test_active_playbooks_skip_all_mutating_groups(tmp_path: Path) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(SMOKE_ACTIVE="1", LIVE_SKIP="10-meta")
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    actual = recorded_calls(calls)
    assert ["soar", "users", "list"] in actual
    assert not any(
        "create" in call
        or "update" in call
        or "delete" in call
        or "import" in call
        or "ingest" in call
        for call in actual
    )
    for group in (
        "20-containers",
        "30-vault",
        "40-lists",
        "50-indicators-search",
        "60-cases",
        "70-assets-actions",
        "80-playbooks-functions",
        "100-ingest",
    ):
        assert f"SKIPPED {group}: active playbooks" in result.stdout
    assert "LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS=1" in result.stdout


def test_failed_preflight_blocks_mutating_groups(tmp_path: Path) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(SMOKE_LIST_FAIL="1", LIVE_ONLY="20-containers,70-assets-actions")
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    actual = recorded_calls(calls)
    assert not any("create" in call for call in actual)
    assert ["soar", "actions", "list"] not in actual
    for group in ("20-containers", "70-assets-actions"):
        assert f"SKIPPED {group}: active playbooks" in result.stdout


def test_active_playbooks_override(tmp_path: Path) -> None:
    env, calls = stub_environment(tmp_path)
    env.update(
        SMOKE_ACTIVE="1",
        LIVE_ONLY="70-assets-actions",
        LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS="1",
    )
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert ["soar", "actions", "list"] in recorded_calls(calls)
    assert "SKIPPED 70-assets-actions: active playbooks" not in result.stdout
