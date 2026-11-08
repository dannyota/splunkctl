"""Offline syntax and command-group coverage checks for the live smoke test."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("live smoke script tests require bash on PATH", allow_module_level=True)

ROOT = Path(__file__).parents[1]
SCRIPTS = [
    ROOT / "scripts/live-smoke.sh",
    *sorted((ROOT / "scripts/live-smoke.d").glob("*.sh")),
]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax(script: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [BASH, "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_every_siem_group_has_step() -> None:
    tree = json.loads((ROOT / "docs/commands.json").read_text())
    excluded = {"soar", "mcp", "auth", "completion", "commands", "docs"}
    groups = {c["name"] for c in tree["commands"]} - excluded
    source = "\n".join(p.read_text() for p in SCRIPTS)
    steps = set(re.findall(r'^\s*step "([a-z-]+)(?:[ :"]|$)', source, re.M))
    assert not groups - steps, f"Missing smoke steps: {sorted(groups - steps)}"


@pytest.mark.parametrize("payload,expected", [("{}", 0), ("invalid json", 1)])
def test_commands_only_never_calls_live_groups(
    tmp_path: Path, payload: str, expected: int
) -> None:
    binary = tmp_path / "splunkctl-stub"
    binary.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$*" != "commands --json" ]; then exit 99; fi\n'
        f"printf '%s\\n' '{payload}'\n"
    )
    binary.chmod(0o755)
    env = {
        **os.environ,
        "SPLUNKCTL": str(binary),
        "LIVE_PYTHON": sys.executable,
        "LIVE_ONLY": "commands",
        "LIVE_SKIP": "",
    }
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPTS[0])], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert f"RESULT: {expected} failure(s)" in result.stdout
    assert "SKIPPED search: not in LIVE_ONLY" in result.stdout


def _leaves(node: dict, prefix: tuple[str, ...] = ()) -> set[str]:
    path = (*prefix, node["name"])
    children = node.get("subcommands", [])
    if not children:
        return {" ".join(path)}
    return set().union(*(_leaves(child, path) for child in children))


def _invoked_commands(source: str, leaves: set[str]) -> set[str]:
    """Recognize CLI calls and expand the script's simple shell verb loops."""
    import shlex

    source = source.replace("\\\n", " ")
    loop = r"\bfor (\w+) in ([^;\n]+); do(.*?)\bdone\b"

    def expand(match: re.Match) -> str:
        variable, values, body = match.groups()
        return "\n".join(
            body.replace(f"${variable}", value) for value in shlex.split(values)
        )

    source = re.sub(loop, expand, source, flags=re.S)
    paths = {name: name.split() for name in leaves}
    invoked = set()
    for line in source.splitlines():
        words = shlex.split(line, comments=True)
        if "$S" in words:
            args = words[words.index("$S") + 1 :]
        elif words and words[0] in {"check_json", "error_kind"}:
            args = words[2:]
        else:
            continue
        for name, path in paths.items():
            if any(args[i : i + len(path)] == path for i in range(len(args))):
                invoked.add(name)
    return invoked


def test_every_non_soar_leaf_is_invoked_or_documented() -> None:
    tree = json.loads((ROOT / "docs/commands.json").read_text())
    leaves = set().union(*(_leaves(node) for node in tree["commands"]))
    leaves = {name for name in leaves if not name.startswith("soar ")}
    source = "\n".join(p.read_text() for p in SCRIPTS)
    invoked = _invoked_commands(source, leaves)
    uncovered = (ROOT / "scripts/live-smoke.d/UNCOVERED.md").read_text()
    listed = set(re.findall(r"^- `([^`]+)`: .+", uncovered, re.M)) - {"soar *"}
    assert not leaves - invoked - listed, sorted(leaves - invoked - listed)
    assert not listed - leaves, f"Stale documentation: {sorted(listed - leaves)}"
    assert not listed & invoked, f"Now covered: {sorted(listed & invoked)}"


def test_leaf_guard_ignores_mentions_and_expands_verb_loops() -> None:
    source = """
# "$S" hec send
skip 'hec send: unavailable'
for verb in cluster shcluster; do expect_ok "$S" server "$verb" --json; done
for verb in show ldap; do
    expect_ok "$S" server auth "$verb" --json
done
check_json 'len(d) == 1' search oneshot '| makeresults'
"""
    leaves = {
        "hec send",
        "server cluster",
        "server shcluster",
        "server auth show",
        "server auth ldap",
        "search oneshot",
    }
    assert _invoked_commands(source, leaves) == leaves - {"hec send"}


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
    respond([{'name': state['index']}], missing=not state['index'])
if args[:2] == ['hec', 'create']:
    state['token_index'] = args[args.index('--index') + 1]
    state['token'] = args[args.index('--name') + 1]
    state['token_disabled'] = '0'
    respond()
if args[:2] == ['hec', 'delete']:
    state['token'] = None
    respond()
if args[:2] == ['hec', 'get']:
    respond([{'disabled': state['token_disabled']}], missing=not state['token'])
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
    import sys

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
        [BASH, str(SCRIPTS[0])], env=env, capture_output=True, text=True, check=False
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
