"""Exercise the raw API smoke without an instance or public response output."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")
ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(BASH is None, reason="bash required")
@pytest.mark.parametrize("allows_write", [False, True])
def test_api_smoke_checks_refusal_and_hides_bodies(tmp_path, allows_write):
    binary = tmp_path / "stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
state = Path(os.environ['SMOKE_STATE'])
raw = sys.argv[1:]
a = [x for x in raw if x not in ('--json', '--yes', '--read-only')]
def reply(data):
    print(json.dumps(data))
def error(kind):
    reply_stderr = {'error': {'kind': kind, 'http_status': None,
                             'message': 'read-only: outputlookup'}}
    print(json.dumps(reply_stderr), file=sys.stderr)
    sys.exit(1)
if a[:2] == ['search', 'oneshot']:
    if 'outputlookup' in a[2]: error('permission')
    reply([{'count': '1'}]); sys.exit(0)
assert a[0] == 'api', a
verb, path = a[1:3]
if verb == 'get':
    if path == 'server/info' or '--describe' in a:
        reply([{'private': 'sensitive-response-marker'}]); sys.exit(0)
    if not state.exists(): error('not_found')
    reply([{'entry': [{'content': {'description': state.read_text(),
                                  'private': 'sensitive-response-marker'}}]}])
elif '--yes' not in raw:
    reply([])
elif verb == 'post':
    if '--read-only' in raw:
        if os.environ['ALLOW_WRITE'] == '0': error('permission')
        state.write_text('sc_live_after')
    else:
        state.write_text('sc_live_before')
    reply([{'private': 'sensitive-response-marker'}])
elif verb == 'delete':
    state.unlink(missing_ok=True)
    reply([])
else:
    raise AssertionError(a)
"""
    )
    binary.chmod(0o755)
    harness = r"""
set -uo pipefail
S=$SMOKE_BINARY PY=$SMOKE_PYTHON T=$SMOKE_TMP N=sc_live_test fail=0
selected() { [ "$1" = api ]; }
step() { :; }
bad() { echo "FAIL $*"; fail=$((fail+1)); }
defer() { :; }
is_not_found() {
    [ "$1" = 1 ] && "$PY" - "$2" <<'PYNOTFOUND'
import json, sys
assert json.load(open(sys.argv[1]))["error"]["kind"] == "not_found"
PYNOTFOUND
}
. "$SMOKE_SCRIPT"
exit "$fail"
"""
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SMOKE_BINARY": str(binary),
            "SMOKE_PYTHON": sys.executable,
            "SMOKE_TMP": str(tmp_path),
            "SMOKE_STATE": str(tmp_path / "state"),
            "SMOKE_SCRIPT": str(ROOT / "scripts/live-smoke.d/40-api.sh"),
            "ALLOW_WRITE": str(int(allows_write)),
        },
    )
    assert (result.returncode == 0) is not allows_write, result.stdout + result.stderr
    assert "sensitive-response-marker" not in result.stdout + result.stderr
