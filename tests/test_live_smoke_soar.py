"""Offline SOAR runner selection, licensing gate, and shared cleanup mechanics."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import click
import pytest

from splunkctl.main import cli

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("live smoke script tests require bash on PATH", allow_module_level=True)

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts/live-smoke-soar.sh"
LIBRARY = ROOT / "scripts/live-smoke-lib.sh"


@pytest.mark.parametrize(
    "script",
    sorted((ROOT / "scripts/live-smoke-soar.d").glob("*.sh")),
    ids=lambda p: p.name,
)
def test_smoke_cli_options(script: Path) -> None:
    """Check static command paths and options without executing live mutations."""
    for line in script.read_text().replace("\\\n", " ").splitlines():
        if '"$S" soar ' not in line:
            continue
        invocation = line.split('"$S" ', 1)[1]
        lexer = shlex.shlex(invocation, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        tokens = []
        for token in lexer:
            if token and token[0] in ";&|<>":
                break
            tokens.append(token)
        command = cli
        while isinstance(command, click.Group):
            name = tokens.pop(0)
            if "$" in name:
                break  # Dynamic command names cannot be resolved statically.
            child = command.get_command(click.Context(command), name)
            assert child is not None, f"{script.name}: unknown command {name}"
            command = child
        else:
            options = {
                opt: param
                for owner in (cli, command)
                for param in owner.params
                if isinstance(param, click.Option)
                for opt in (*param.opts, *param.secondary_opts)
            }
            while tokens:
                token = tokens.pop(0)
                if not token.startswith("--") or "$" in token:
                    continue
                option = token.split("=", 1)[0]
                assert option in options, (
                    f"{script.name}: {invocation}: unknown {option}"
                )
                param = options[option]
                if not param.is_flag and "=" not in token:
                    del tokens[: param.nargs]


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


def test_playbook_collision_blocks_import_and_cleanup(tmp_path: Path) -> None:
    env, calls = stub_environment(tmp_path)
    binary = Path(env["SPLUNKCTL"])
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['SMOKE_CALLS']).open('a') as f:\n"
        "    f.write(json.dumps(args) + '\\n')\n"
        "rows = [{'id': 7, 'name': 'fixture/fixture', 'labels': ['events']}]\n"
        "print(json.dumps(rows\n"
        "      if '--name' in args else []))\n"
    )
    env.update(
        SMOKE_SCRIPT=str(ROOT / "scripts/live-smoke-soar.d/80-playbooks-functions.sh"),
        SMOKE_TMP=str(tmp_path),
    )
    harness = r"""
S=$SPLUNKCTL PY=$LIVE_PYTHON T=$SMOKE_TMP N=fixture
soar_selected() { return 1; }
ensure_event() { return 0; }
expect_ok() { "$@"; }
capture() { local out=$1; shift; "$@" > "$out"; }
bad() { echo "FAIL $*"; }
defer() { echo "UNEXPECTED cleanup registration"; }
. "$SMOKE_SCRIPT"
soar_playbooks_functions
"""
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", harness], env=env, capture_output=True, text=True, check=False
    )
    assert "automation fixture name already exists" in result.stdout
    assert "UNEXPECTED" not in result.stdout
    actual = recorded_calls(calls)
    assert [
        "soar",
        "playbooks",
        "list",
        "--repo",
        "local",
        "--name",
        "fixture/fixture",
        "--json",
    ] in actual
    assert not any("import" in call for call in actual)


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


@pytest.mark.parametrize(
    "mode,listed,expected",
    [
        ("disabled", False, 0),
        ("missing", False, 0),
        ("active", False, 1),
        ("disabled", True, 1),
        ("error", False, 1),
    ],
)
def test_asset_absence(tmp_path: Path, mode: str, listed: bool, expected: int) -> None:
    env, _ = stub_environment(tmp_path)
    binary = Path(env["SPLUNKCTL"])
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "if 'get' in sys.argv:\n"
        + (
            "    print(json.dumps({'error': {'kind': 'not_found'}})); sys.exit(1)\n"
            if mode == "missing"
            else "    print(json.dumps({'error': {'kind': 'auth'}})); sys.exit(1)\n"
            if mode == "error"
            else "    print(json.dumps("
            + repr({"id": 7, "disabled": mode == "disabled"})
            + "))\n"
        )
        + f"else: print(json.dumps({[{'id': 7}] if listed else []}))\n"
    )
    # Load helper definitions without starting the runner or its EXIT trap.
    prefix = RUNNER.read_text().split('command -v "$S"')[0]
    harness = tmp_path / "asset-helper.sh"
    prefix = prefix.replace(
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        f'HERE="{ROOT / "scripts"}"',
    ).replace("trap soar_finish EXIT", "")
    harness.write_text(prefix + "\nasset_absent 7\n")
    result = subprocess.run(  # noqa: S603
        [BASH, str(harness)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == expected, result.stdout + result.stderr
