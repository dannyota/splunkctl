"""Offline verification of HEC fixture handling and setting restoration."""

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

RUNNER = Path(__file__).parents[1] / "scripts/live-smoke.sh"


HEC_STUB = r"""
import json, os, sys
from pathlib import Path
p = Path(os.environ['HEC_STATE'])
state = json.loads(p.read_text())
args = [a for a in sys.argv[1:] if a not in ('--json', '--yes')]
if '--timeout' in args:
    i = args.index('--timeout')
    del args[i:i+2]
state['calls'].append(args)
def respond(value=None, missing=False):
    p.write_text(json.dumps(state))
    if missing:
        print(json.dumps({'error': {'kind': 'not_found'}}), file=sys.stderr)
        sys.exit(1)
    if value is not None:
        print(json.dumps(value))
    sys.exit(0)
if args[:2] == ['hec', 'settings']:
    if '--enable' in args: state['disabled'] = '0'
    if '--disable' in args: state['disabled'] = '1'
    respond([{'disabled': state['disabled'], 'port': '8088', 'enableSSL': '0'}])
if args[:2] == ['indexes', 'create']:
    state['index'] = args[args.index('--name') + 1]
    respond()
if args[:2] == ['indexes', 'delete']:
    state['index'] = None
    respond()
if args[:2] == ['indexes', 'get']:
    respond([{'name': state.get('index')}], missing=not state.get('index'))
if args[:2] == ['hec', 'create']:
    state['token_index'] = args[args.index('--index') + 1]
    state['token'] = args[args.index('--name') + 1]
    state['token_disabled'] = '0'
    respond()
if args[:2] == ['hec', 'delete']:
    state['token'] = None
    respond()
if args[:2] == ['hec', 'get']:
    respond([{'disabled': state.get('token_disabled', '0')}],
            missing=not state.get('token'))
if args[:2] == ['hec', 'list']: respond([])
if args[:2] == ['hec', 'disable']:
    state['token_disabled'] = '1'
    respond()
if args[:2] == ['hec', 'enable']:
    state['token_disabled'] = '0'
    respond()
if args[:2] == ['hec', 'send']:
    p.write_text(json.dumps(state))
    sys.exit(int(os.environ['HEC_SEND_FAIL']))
if args[:2] == ['search', 'oneshot']:
    state['polls'] += 1
    respond([{'count': '0' if state['polls'] == 1 else '1'}])
raise AssertionError(args)
"""


@pytest.mark.parametrize(
    "disabled,send_fail", [("0", False), ("1", False), ("1", True)]
)
def test_hec_send_retries_and_restores_settings(
    tmp_path: Path, disabled: str, send_fail: bool
) -> None:
    binary = tmp_path / "splunkctl-stub"
    binary.write_text(f"#!{sys.executable}\n" + HEC_STUB)
    binary.chmod(0o755)
    state_file = tmp_path / "hec.json"
    state_file.write_text(json.dumps({"disabled": disabled, "calls": [], "polls": 0}))
    env = {
        **os.environ,
        "SPLUNKCTL": str(binary),
        "LIVE_PYTHON": sys.executable,
        "LIVE_ONLY": "hec",
        "LIVE_SKIP": "",
        "LIVE_HEC_URL": "http://127.0.0.1:18088",
        "HEC_STATE": str(state_file),
        "HEC_SEND_FAIL": str(int(send_fail)),
    }
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUNNER)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == int(send_fail), result.stdout + result.stderr
    state = json.loads(state_file.read_text())
    assert state["disabled"] == disabled
    assert state["index"] is None and state["token"] is None
    assert state["token_index"].startswith("sc_live_")
    calls = state["calls"]
    sends = [c for c in calls if c[:2] == ["hec", "send"]]
    assert len(sends) == 1
    send = sends[0]
    assert send[2] == state["token_index"]
    assert send[send.index("--index") + 1] == state["token_index"]
    assert send[send.index("--url") + 1] == "http://127.0.0.1:18088"
    settings_changes = [c for c in calls if c[:2] == ["hec", "settings"] and len(c) > 2]
    assert settings_changes == (
        [["hec", "settings", "--enable"], ["hec", "settings", "--disable"]]
        if disabled == "1"
        else []
    )
    assert state["polls"] == (0 if send_fail else 2)
