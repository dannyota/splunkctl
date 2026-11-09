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
            elif word in {
                "run",
                "expect_ok",
                "expect_fail",
                "capture",
                "api_capture",
                "defer",
            }:
                j = i + (2 if word in {"capture", "api_capture"} else 1)
                if j >= len(words) or words[j] != "$S":
                    continue
                args = words[j + 1 :]
            else:
                continue
            while args and args[0].startswith("--"):
                option = args.pop(0)
                if (
                    option not in {"--json", "--yes", "--read-only"}
                    and "=" not in option
                    and args
                ):
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
