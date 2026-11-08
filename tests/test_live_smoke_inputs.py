"""Existing server monitor inputs must remain untouched by smoke runs."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("bash unavailable", allow_module_level=True)
ROOT = Path(__file__).parents[1]
MONITOR = "/" + "tmp"


@pytest.mark.parametrize("existing", [True, False])
def test_monitor_uses_existing_path_and_skips_existing_input(tmp_path, existing):
    stub = tmp_path / "stub"
    calls = tmp_path / "calls"
    stub.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, sys
from pathlib import Path
args = [a for a in sys.argv[1:] if a not in ('--json', '--yes')]
with Path(os.environ['CALLS']).open('a') as f:
    f.write(json.dumps(args) + '\n')
p = Path(os.environ['CALLS'] + '.created')
i = Path(os.environ['CALLS'] + '.index')
d = Path(os.environ['CALLS'] + '.disabled')
if args[:2] == ['inputs', 'get']:
    if os.environ['EXISTING'] == '1' or p.exists():
        disabled = d.read_text() if d.exists() else '1'
        print(json.dumps([{'name': '/tmp', 'disabled': disabled}]))
        sys.exit(0)
    print('{"error":{"kind":"not_found"}}', file=sys.stderr)
    sys.exit(1)
if args[:2] == ['indexes', 'create']: i.touch()
if args[:2] == ['indexes', 'delete']: i.unlink()
if args[:2] == ['indexes', 'get']:
    if i.exists():
        print('[{}]')
        sys.exit(0)
    print('{"error":{"kind":"not_found"}}', file=sys.stderr)
    sys.exit(1)
if args[:2] == ['inputs', 'create']:
    assert args[args.index('--name') + 1] == '/tmp'
    assert '--disabled' in args
    p.touch()
if args[:2] == ['inputs', 'disable']: d.write_text('1')
if args[:2] == ['inputs', 'enable']: d.write_text('0')
if args[:2] == ['inputs', 'delete']: p.unlink()
if args[:2] == ['inputs', 'list']: print(json.dumps([{ "name": "/tmp" }]))
"""
    )
    stub.chmod(0o755)
    result = subprocess.run(  # noqa: S603
        [BASH, str(ROOT / "scripts/live-smoke.sh")],
        env={
            **os.environ,
            "SPLUNKCTL": str(stub),
            "LIVE_PYTHON": sys.executable,
            "LIVE_ONLY": "inputs",
            "LIVE_SKIP": "",
            "LIVE_MONITOR_PATH": MONITOR,
            "CALLS": str(calls),
            "EXISTING": str(int(existing)),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    if existing:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SKIPPED inputs: monitor already exists: /tmp" in result.stdout
        assert recorded == [["inputs", "get", MONITOR]]
    else:
        creates = [c for c in recorded if c[:2] == ["inputs", "create"]]
        assert len(creates) == 1
        assert creates[0][:6] == [
            "inputs",
            "create",
            "--name",
            MONITOR,
            "--kind",
            "monitor",
        ]
        assert "--disabled" in creates[0]
        assert ["inputs", "delete", MONITOR] in recorded
