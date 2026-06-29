"""Tests for the commands (meta) command."""

import json

from click.testing import CliRunner

from splunkctl.main import cli


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
    assert "skill" in names


def test_commands_includes_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    data = json.loads(result.output)
    assert data["version"] == "0.2.0"


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
