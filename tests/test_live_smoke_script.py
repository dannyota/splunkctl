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
SOAR_SCRIPTS = [
    ROOT / "scripts/live-smoke-soar.sh",
    *sorted((ROOT / "scripts/live-smoke-soar.d").glob("*.sh")),
]
LIBRARY = ROOT / "scripts/live-smoke-lib.sh"


@pytest.mark.parametrize(
    "script", [*SCRIPTS, *SOAR_SCRIPTS, LIBRARY], ids=lambda p: p.name
)
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

    # Generated bundle contents are data, not shell command invocations.
    lines = []
    delimiter = None
    for line in source.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        lines.append(line)
        match = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
        if match:
            delimiter = match.group(1)
    source = "\n".join(lines)
    source = source.replace("\\\n", " ")
    loop = r"\bfor (\w+) in ([^;\n]+); do(.*?)\bdone\b"

    def expand(match: re.Match) -> str:
        variable, values, body = match.groups()
        return "\n".join(
            body.replace(f"${{{variable}}}", value).replace(f"${variable}", value)
            for value in shlex.split(values)
        )

    source = re.sub(loop, expand, source, flags=re.S)
    paths = {name: name.split() for name in leaves}
    invoked = set()
    for line in source.splitlines():
        # Preserve quoted separator literals through shlex quote removal.
        line = re.sub(r"(['\"])([;&|(){}]+)\1", "quoted_separator", line)
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        words = list(lexer)
        # Only command words and known executing wrapper argument positions count.
        starts = [0] + [
            i + 1
            for i, word in enumerate(words)
            if word in {";", "&&", "||", "|", "{", ")", "("}
        ]
        for i in starts:
            if i >= len(words):
                continue
            word = words[i]
            if word in {"if", "!", "elif", "then", "do", "else"}:
                i += 1
                if i < len(words) and words[i] == "!":
                    i += 1
                if i >= len(words):
                    continue
                word = words[i]
            if word == "$S":
                args = words[i + 1 :]
            elif word in {"check_json", "error_kind"}:
                args = words[i + 2 :]
            elif word in {"absent", "delete_fixture"}:
                args = words[i + 1 :]
            elif word in {"run", "expect_ok", "expect_fail", "capture", "defer"}:
                j = i + (2 if word == "capture" else 1)
                if j >= len(words) or words[j] != "$S":
                    continue
                args = words[j + 1 :]
            else:
                continue
            while args and args[0].startswith("--"):
                option = args.pop(0)
                if option not in {"--json", "--yes"} and "=" not in option and args:
                    args.pop(0)
            for name, path in paths.items():
                if args[: len(path)] == path:
                    invoked.add(name)
    return invoked


def test_every_non_soar_leaf_is_invoked_or_documented() -> None:
    tree = json.loads((ROOT / "docs/commands.json").read_text())
    leaves = set().union(*(_leaves(node) for node in tree["commands"]))
    leaves = {name for name in leaves if not name.startswith("soar ")}
    source = "\n".join(p.read_text() for p in SCRIPTS)
    invoked = _invoked_commands(source, leaves)
    uncovered = (ROOT / "scripts/live-smoke.d/UNCOVERED.md").read_text()
    listed = set(re.findall(r"^- `([^`]+)`: .+", uncovered, re.M))
    assert not leaves - invoked - listed, sorted(leaves - invoked - listed)
    assert not listed - leaves, f"Stale documentation: {sorted(listed - leaves)}"
    assert not listed & invoked, f"Now covered: {sorted(listed & invoked)}"


def test_every_soar_leaf_is_invoked_or_documented() -> None:
    tree = json.loads((ROOT / "docs/commands.json").read_text())
    soar = next(node for node in tree["commands"] if node["name"] == "soar")
    leaves = _leaves(soar)
    source = "\n".join(p.read_text() for p in SOAR_SCRIPTS)
    invoked = _invoked_commands(source, leaves)
    uncovered = (ROOT / "scripts/live-smoke-soar.d/UNCOVERED.md").read_text()
    listed = set(re.findall(r"^- `([^`]+)`: .+", uncovered, re.M))
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


def test_leaf_guard_matches_only_command_position() -> None:
    source = """
expect_ok "$S" conf get server health
check_json 'True' conf get server cluster
error_kind not_found conf get server shcluster
for verb in health; do expect_ok "$S" server "${verb}"; done
"""
    assert _invoked_commands(
        source, {"conf get", "server health", "server cluster", "server shcluster"}
    ) == {"conf get", "server health"}


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
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(state_file.read_text())["pushes"] == 2


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
            "ADMIN_SCRIPT": str(SCRIPTS[-1]),
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


def test_leaf_guard_ignores_bundle_heredoc() -> None:
    source = '''cat <<'PYBUNDLE'
"""A multiline Python string
expect_ok "$S" soar users delete
"""
PYBUNDLE
expect_ok "$S" soar users list
'''
    assert _invoked_commands(source, {"soar users list", "soar users delete"}) == {
        "soar users list"
    }


@pytest.mark.parametrize(
    "source",
    [
        'echo "$S" soar users delete',
        'skip "$S" soar users delete',
        'log "$S" soar users delete',
        'echo then "$S" soar users delete',
        'echo ";" "$S" soar users delete',
        '# "$S" soar users delete',
        "echo 'expect_ok \"$S\" soar users delete'",
        'cat <<EOF\n"$S" soar users delete\nEOF',
    ],
)
def test_leaf_guard_rejects_message_text(source: str) -> None:
    assert not _invoked_commands(source, {"soar users delete"})


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "run ",
        "expect_ok ",
        "expect_fail ",
        'capture "$T/out" ',
        "defer ",
        "if ",
        "if ! ",
        'case "$group" in users) ',
    ],
)
def test_leaf_guard_accepts_executable_positions(prefix: str) -> None:
    leaf = "soar users list"
    assert _invoked_commands(prefix + '"$S" ' + leaf, {leaf}) == {leaf}
