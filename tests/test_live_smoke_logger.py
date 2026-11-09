"""Runtime logger cleanup survives a failed read-back step."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("later_failure", [False, True])
def test_logger_smoke_restores_after_later_failure(tmp_path, later_failure):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash required")
    root = Path(__file__).parents[1]
    binary = tmp_path / "stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
p = Path(os.environ['LOGGER_STATE'])
s = json.loads(p.read_text())
a = [x for x in sys.argv[1:] if x != '--json']
s['calls'].append(a)
failed = False
if a[:3] == ['server', 'log-level', 'set']:
    if '--yes' in a: s['level'] = a[4]
    result = [{'level': s['level']}]
elif a[:3] == ['server', 'log-level', 'get']:
    if s['level'] == 'DEBUG' and os.environ['LATER_FAILURE'] == '1' and not s['failed']:
        s['failed'] = failed = True
    result = [{'level': s['level']}]
elif a[-1] == 'queues':
    result = [dict(queue='indexQueue', current=0, maximum=1,
                   unit='bytes', fill_ratio=0)]
elif a[-1] == 'indexer':
    result = [dict(name='indexer', status='normal', reason='', average_KBps=0)]
else:
    result = [dict(capacity=100, available=50, unit='MB', fs_type=None)]
p.write_text(json.dumps(s))
if failed:
    print('injected later failure', file=sys.stderr)
    sys.exit(1)
print(json.dumps(result))
"""
    )
    binary.chmod(0o755)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"level": "INFO", "calls": [], "failed": False}))
    harness = tmp_path / "run.sh"
    harness.write_text("""set -uo pipefail
T=$(mktemp -d)
fail=0
: > "$T/cleanup.sh"
. "$LIB"
. "$API"
. "$STEPS"
""")
    result = subprocess.run(  # noqa: S603
        [bash, str(harness)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "S": str(binary),
            "PY": sys.executable,
            "LIB": str(root / "scripts/live-smoke-lib.sh"),
            "API": str(root / "scripts/live-smoke.d/40-api.sh"),
            "STEPS": str(root / "scripts/live-smoke.d/45-acl-server.sh"),
            "LIVE_ONLY": "server",
            "LIVE_SKIP": "",
            "LOGGER_STATE": str(state_file),
            "LATER_FAILURE": str(int(later_failure)),
        },
    )
    assert result.returncode == int(later_failure), result.stdout + result.stderr
    state = json.loads(state_file.read_text())
    assert state["level"] == "INFO"
    assert state["failed"] == later_failure
    assert state["calls"][-2:] == [
        ["server", "log-level", "set", "TcpOutputProc", "INFO", "--yes"],
        ["server", "log-level", "get", "TcpOutputProc"],
    ]
