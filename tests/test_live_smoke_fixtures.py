"""Offline regression checks for live smoke fixture lifecycle behavior."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_live_smoke_script import BASH, ROOT, SCRIPTS


@pytest.mark.parametrize("mode", ["partial", "missing", "delete_failure", "existing"])
def test_fixture_failure_cleanup(tmp_path: Path, mode: str) -> None:
    binary = tmp_path / "stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
root = Path(os.environ['TMPDIR'])
mode = os.environ['FIXTURE_MODE']
args = [a for a in sys.argv[1:] if a not in ('--json', '--yes')]
with (root / 'calls').open('a') as f:
    f.write(' '.join(args) + '\n')
if args[:2] == ['indexes', 'get']:
    if mode == 'existing':
        print('[{"name":"existing"}]')
        sys.exit(0)
    print('{"error":{"kind":"not_found"}}', file=sys.stderr)
    sys.exit(1)
if args[:2] == ['indexes', 'create']:
    cleanup = next(root.glob('sc-live.*/cleanup.sh')).read_text()
    assert 'indexes delete' in cleanup
    sys.exit(1)
if args[:2] == ['indexes', 'delete']:
    if mode == 'delete_failure': sys.exit(2)
    if mode == 'missing':
        print('{"error":{"kind":"not_found"}}', file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
raise AssertionError(args)
"""
    )
    binary.chmod(0o755)
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPTS[0])],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SPLUNKCTL": str(binary),
            "LIVE_PYTHON": sys.executable,
            "LIVE_ONLY": "indexes",
            "LIVE_SKIP": "",
            "TMPDIR": str(tmp_path),
            "FIXTURE_MODE": mode,
        },
    )
    assert result.returncode == 1, result.stdout + result.stderr
    calls = (tmp_path / "calls").read_text()
    assert ("indexes delete" in calls) == (mode != "existing")
    retained = list(tmp_path.glob("sc-live.*"))
    assert bool(retained) == (mode == "delete_failure")
    if retained:
        assert str(retained[0]) in result.stdout
        assert "indexes delete" in (retained[0] / "remaining.sh").read_text()


def test_state_push_contains_only_fixture_rule(tmp_path: Path) -> None:
    binary = tmp_path / "stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys, yaml
from pathlib import Path
p = Path(os.environ['STATE_FILE'])
state = json.loads(p.read_text()) if p.exists() else {}
args = [a for a in sys.argv[1:] if a not in ('--json', '--yes')]
group, verb = args[:2]
def respond(rows=None):
    p.write_text(json.dumps(state))
    if rows is not None: print(json.dumps(rows))
    sys.exit(0)
if group in ('rules', 'lookups', 'dashboards'):
    if verb in ('create', 'upload'):
        state[group] = args[args.index('--name')+1] if '--name' in args else args[2]
        respond()
    if verb == 'delete':
        state.pop(group, None)
        respond()
    if verb == 'get':
        if group not in state:
            print('{"error":{"kind":"not_found"}}', file=sys.stderr)
            sys.exit(1)
        respond([{'description': 'sc_live_state_changed'}])
if group == 'api':
    name = state['rules']
    if verb == 'get':
        assert args[2] == '/servicesNS/-/search/saved/searches/' + name
        fixture = json.loads(Path(os.environ['ACL_FIXTURE']).read_text())
        entry = fixture['entry'][0]
        entry['name'] = name
        entry['id'] = ('https://splunk-host/servicesNS/nobody/search/'
                       'saved/searches/' + name)
        respond([fixture])
    if verb == 'delete':
        assert args[2] == '/servicesNS/nobody/search/saved/searches/' + name
        state.pop('rules')
        state['shared_cleanup'] = True
        respond()
if group == 'state':
    target = Path(args[args.index('--dir')+1])
    if verb == 'pull':
        target.mkdir()
        (target/'rules.yml').write_text(yaml.safe_dump([
            {'name': state['rules']}, {'name': 'unrelated', 'description': 'old'}]))
        (target/'lookups').mkdir()
        (target/'dashboards').mkdir()
        respond()
    if verb == 'diff':
        assert len(yaml.safe_load((target/'rules.yml').read_text())) == 2
        respond([{'name': state['rules'],
                  'change': 'unchanged' if state.get('applied') else 'modified'}])
    if verb == 'push':
        docs = yaml.safe_load((target/'rules.yml').read_text())
        assert [d['name'] for d in docs] == [state['rules']], docs
        assert sorted(f.name for f in target.iterdir()) == ['rules.yml']
        state['pushes'] = state.get('pushes', 0) + 1
        applied = '--yes' in sys.argv
        if applied: state['applied'] = True
        report = {'applied': applied, 'changes': [{'name': state['rules']}]}
        Path(args[args.index('--report')+1]).write_text(json.dumps(report))
        respond()
raise AssertionError(args)
"""
    )
    binary.chmod(0o755)
    state_file = tmp_path / "state.json"
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPTS[0])],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SPLUNKCTL": str(binary),
            "LIVE_PYTHON": sys.executable,
            "LIVE_ONLY": "state",
            "LIVE_SKIP": "",
            "STATE_FILE": str(state_file),
            "ACL_FIXTURE": str(
                ROOT
                / "tests/fixtures/live/splunk-10.6.1.1"
                / "acl-set-saved-search-getback.json"
            ),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(state_file.read_text())
    assert state["pushes"] == 2
    assert state["shared_cleanup"] is True
    assert "rules" not in state


@pytest.mark.parametrize("mode", ["enables", "empty", "error", "transient"])
def test_datamodel_acceleration_poll(tmp_path: Path, mode: str) -> None:
    binary = tmp_path / "stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
p = Path(os.environ['ACCEL_STATE'])
state = json.loads(p.read_text())
args = sys.argv[1:]
state['calls'].append(args)
mode = os.environ['ACCEL_MODE']
if args[:2] == ['datamodels', 'list']:
    print('[{"name":"Alerts"}]' if '--app' in args else '[]')
elif args[:2] == ['--json', 'datamodels'] and args[2] == 'acceleration':
    print('[{"enabled": true}]')
elif args[:2] == ['--json', 'datamodels'] and args[2] == 'get':
    print('[{"acceleration_enabled": true, "acceleration_earliest_time": "-15m"}]')
elif args[:2] == ['--timeout', '30']:
    assert args[:2] == ['--timeout', '30'], args
    state['polls'] += 1
    if mode == 'error' or (mode == 'transient' and state['polls'] > 1):
        p.write_text(json.dumps(state))
        print('Error: poll failed', file=sys.stderr)
        sys.exit(2)
    enabled = mode == 'enables' and state['polls'] >= 3
    row = {'enabled': enabled, 'has_summary': False, 'percent_complete': None,
           'size': None, 'earliest_summarized': None, 'latest_summarized': None}
    state['last_json'] = json.dumps([row])
    print(state['last_json'])
elif args[:2] not in (['datamodels', 'acceleration'], ['datamodels', 'get'],
                       ['datamodels', 'accelerate'], ['datamodels', 'rebuild']):
    raise AssertionError(args)
p.write_text(json.dumps(state))
"""
    )
    binary.chmod(0o755)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"calls": [], "polls": 0}))
    # Source only the admin steps, with CIM already installed by this harness.
    harness = r"""
set -uo pipefail
S=$SPLUNKCTL PY=$LIVE_PYTHON T=$POLL_TMP
fail=0
selected() { [ "$1" = datamodels ]; }
step() { :; }
run() { "$@"; }
bad() { echo "FAIL $*"; fail=$((fail+1)); }
skip() { echo "SKIPPED $*"; }
expect_ok() { "$@" || bad 'expected exit 0'; }
capture() { local file=$1; shift; "$@" > "$file" || { bad 'capture'; return 1; }; }
check_json() {
    local e=$1; shift
    "$S" --json "$@" > "$T/result.json" || bad 'check_json'
    local chk='import json,sys;d=json.load(open(sys.argv[1]));assert eval(sys.argv[2])'
    "$PY" -c "$chk" "$T/result.json" "$e" || bad "JSON assertion: $e"
}
cim_installed=1
. "$ADMIN_SCRIPT"
exit "$fail"
"""
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SPLUNKCTL": str(binary),
            "LIVE_PYTHON": sys.executable,
            "POLL_TMP": str(tmp_path),
            "ADMIN_SCRIPT": str(ROOT / "scripts/live-smoke.d/30-admin.sh"),
            "ACCEL_STATE": str(state_file),
            "ACCEL_MODE": mode,
            "LIVE_ACCEL_WAIT": "2",
            "LIVE_ACCEL_INTERVAL": "0",
        },
        timeout=10,
    )
    state = json.loads(state_file.read_text())
    assert result.returncode == (1 if mode in ("error", "transient") else 0), (
        result.stdout + result.stderr
    )
    assert len(re.findall(r"^FAIL ", result.stdout, re.M)) == (
        1 if mode in ("error", "transient") else 0
    )
    rebuilds = [c for c in state["calls"] if c[:2] == ["datamodels", "rebuild"]]
    skipped = [
        s
        for s in result.stdout.splitlines()
        if s.startswith("SKIPPED datamodels rebuild:")
    ]
    assert len(rebuilds) == (1 if mode == "enables" else 0)
    if mode == "enables":
        assert state["polls"] == 3
        assert "--yes" in rebuilds[0]
        assert not skipped
    else:
        assert len(skipped) == 1
        assert (
            state["last_json"] if mode != "error" else "Error: poll failed"
        ) in skipped[0]
