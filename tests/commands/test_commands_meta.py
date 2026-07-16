"""Tests for the commands (meta) command."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from splunkctl.main import cli

COMMANDS_DIR = Path(__file__).resolve().parent.parent.parent / "splunkctl" / "commands"


def test_commands_json_output() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "version" in data
    assert "commands" in data
    tree = data["commands"]
    assert isinstance(tree, list)
    names = [c["name"] for c in tree]
    assert "search" in names
    assert "rules" in names
    assert "alerts" in names
    assert "dashboards" in names
    assert "commands" in names
    assert "mcp" in names


def test_commands_includes_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    data = json.loads(result.output)
    assert data["version"] == "0.10.1"


def test_commands_search_has_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    search = next(c for c in tree if c["name"] == "search")
    assert "subcommands" in search
    sub_names = [s["name"] for s in search["subcommands"]]
    assert "run" in sub_names
    assert "export" in sub_names
    assert "oneshot" in sub_names
    assert "jobs" in sub_names


def test_commands_params_included() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    search = next(c for c in tree if c["name"] == "search")
    run_cmd = next(s for s in search["subcommands"] if s["name"] == "run")
    assert "params" in run_cmd
    param_names = [p["name"] for p in run_cmd["params"]]
    assert "spl" in param_names


def test_commands_argument_vs_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    search = next(c for c in tree if c["name"] == "search")
    run_cmd = next(s for s in search["subcommands"] if s["name"] == "run")
    spl = next(p for p in run_cmd["params"] if p["name"] == "spl")
    assert spl["kind"] == "argument"
    earliest = next(p for p in run_cmd["params"] if p["name"] == "earliest")
    assert earliest["kind"] == "option"


def test_commands_required_params() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    dashboards = next(c for c in tree if c["name"] == "dashboards")
    create = next(s for s in dashboards["subcommands"] if s["name"] == "create")
    name_p = next(p for p in create["params"] if p["name"] == "name")
    assert name_p["required"] is True


def test_commands_flags_have_type_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    inputs = next(c for c in tree if c["name"] == "inputs")
    create = next(s for s in inputs["subcommands"] if s["name"] == "create")
    disabled = next(p for p in create["params"] if p["name"] == "disabled")
    assert disabled["type"] == "flag"


def test_commands_defaults_native_types() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    search = next(c for c in tree if c["name"] == "search")
    run_cmd = next(s for s in search["subcommands"] if s["name"] == "run")
    limit = next(p for p in run_cmd["params"] if p["name"] == "limit")
    assert limit["default"] == 100
    assert isinstance(limit["default"], int)


def test_commands_choice_values() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    inputs = next(c for c in tree if c["name"] == "inputs")
    create = next(s for s in inputs["subcommands"] if s["name"] == "create")
    kind = next(p for p in create["params"] if p["name"] == "kind")
    assert "choices" in kind
    assert "monitor" in kind["choices"]
    assert "tcp" in kind["choices"]


def test_commands_help_not_in_params() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    for cmd in tree:
        if "params" in cmd:
            names = [p["name"] for p in cmd["params"]]
            assert "help" not in names
        if "subcommands" in cmd:
            for sub in cmd["subcommands"]:
                if "params" in sub:
                    names = [p["name"] for p in sub["params"]]
                    assert "help" not in names


def test_commands_option_flags_included() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    tree = json.loads(result.output)["commands"]
    search = next(c for c in tree if c["name"] == "search")
    run_cmd = next(s for s in search["subcommands"] if s["name"] == "run")
    earliest = next(p for p in run_cmd["params"] if p["name"] == "earliest")
    assert "flags" in earliest
    assert "--earliest" in earliest["flags"]


def test_commands_global_options() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    assert "global_options" in data
    names = [o["name"] for o in data["global_options"]]
    assert "fmt" in names
    assert "yes" in names


def test_commands_global_options_includes_profile() -> None:
    """--profile is picked up automatically via Click introspection."""
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    profile_opt = next(o for o in data["global_options"] if o["name"] == "profile")
    assert "--profile" in profile_opt["flags"]


def test_commands_note_field() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)
    assert "note" in data
    assert "guarded" in data["note"]
    assert "dry-run" in data["note"]


def test_guarded_markers_present() -> None:
    """Mutation commands expose guarded=true in commands JSON."""
    result = CliRunner().invoke(cli, ["commands"])
    data = json.loads(result.output)

    def _collect(nodes: list[dict[str, object]]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for n in nodes:
            if "subcommands" in n:
                out.update(
                    _collect(n["subcommands"])  # type: ignore[arg-type]
                )
            else:
                if n.get("guarded"):
                    out[str(n["name"])] = True
        return out

    guarded = _collect(data["commands"])
    assert len(guarded) > 10, f"Expected many guarded cmds, got {len(guarded)}"
    for expected in ("create", "delete", "update", "enable", "disable"):
        assert expected in guarded, f"{expected} should be guarded"


def test_guard_check_has_decorator_tripwire() -> None:
    """AST tripwire: every function calling guard.check must have @guard.guarded."""
    missing: list[str] = []
    for py in sorted(COMMANDS_DIR.glob("*.py")):
        if py.name.startswith("_"):
            continue
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls_guard = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "check"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "guard"
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            )
            if not calls_guard:
                continue
            has_decorator = any(
                (
                    isinstance(d, ast.Attribute)
                    and d.attr == "guarded"
                    and isinstance(d.value, ast.Name)
                    and d.value.id == "guard"
                )
                or (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "guarded"
                )
                for d in node.decorator_list
            )
            if not has_decorator:
                missing.append(f"{py.name}:{node.name}")
    assert not missing, (
        f"Functions call guard.check() but lack @guard.guarded: {missing}"
    )


# ---------------------------------------------------------------------------
# Per-command @guarded visibility in commands --json
# ---------------------------------------------------------------------------


def _collect_guarded(nodes: list[dict[str, Any]]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for n in nodes:
        if "subcommands" in n:
            out.update(_collect_guarded(n["subcommands"]))
        elif n.get("guarded"):
            out[str(n["name"])] = True
    return out


def _collect_guarded_full_path(
    nodes: list[dict[str, Any]],
    prefix: str = "",
) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for n in nodes:
        path = f"{prefix}.{n['name']}" if prefix else str(n["name"])
        if "subcommands" in n:
            out.update(_collect_guarded_full_path(n["subcommands"], path))
        elif n.get("guarded"):
            out[path] = True
    return out


class TestGuardedMarkers:
    def test_vault_upload_guarded(self) -> None:
        """vault upload reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        guarded = _collect_guarded(data["commands"])
        assert "upload" in guarded, "vault upload should be guarded"

    def test_vault_delete_guarded(self) -> None:
        """vault delete reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        guarded = _collect_guarded(data["commands"])
        assert "delete" in guarded, "vault delete should be guarded"

    def test_notes_add_guarded(self) -> None:
        """notes add reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.add" in soar_cmds, "notes add should be guarded"

    def test_notes_delete_guarded(self) -> None:
        """notes delete reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.delete" in soar_cmds, "notes delete should be guarded"

    def test_notes_comment_guarded(self) -> None:
        """notes comment reports guarded=true in commands --json."""
        result = CliRunner().invoke(cli, ["commands"])
        data = json.loads(result.output)
        soar_cmds = _collect_guarded_full_path(data["commands"])
        assert "soar.notes.comment" in soar_cmds, "notes comment should be guarded"
