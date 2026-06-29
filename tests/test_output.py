"""Tests for splunkctl.output."""

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from splunkctl import output


def _make_ctx(**flags: object) -> tuple[click.Context, CliRunner]:
    """Build a Click context with format flags."""

    @click.command()
    @click.pass_context
    def dummy(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update(
            {"json": False, "format": None, "fields": None, "out": None, **flags}
        )
        output.render(ctx, _SAMPLE)

    runner = CliRunner()
    return dummy, runner  # type: ignore[return-value]


_SAMPLE = [
    {"name": "idx_main", "size": 1024},
    {"name": "idx_summary", "size": 512},
]


def test_json_format() -> None:
    cmd, runner = _make_ctx(format="json")
    result = runner.invoke(cmd)
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "idx_main"


def test_json_flag() -> None:
    cmd, runner = _make_ctx(json=True)
    result = runner.invoke(cmd)
    parsed = json.loads(result.output)
    assert len(parsed) == 2


def test_jsonl_format() -> None:
    cmd, runner = _make_ctx(format="jsonl")
    result = runner.invoke(cmd)
    lines = result.output.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "idx_main"


def test_csv_format() -> None:
    cmd, runner = _make_ctx(format="csv")
    result = runner.invoke(cmd)
    lines = result.output.strip().split("\n")
    assert lines[0] == "name,size"
    assert "idx_main" in lines[1]


def test_table_format() -> None:
    cmd, runner = _make_ctx(format="table")
    result = runner.invoke(cmd)
    assert "idx_main" in result.output
    assert "idx_summary" in result.output


def test_fields_projection() -> None:
    cmd, runner = _make_ctx(format="json", fields="name")
    result = runner.invoke(cmd)
    parsed = json.loads(result.output)
    assert list(parsed[0].keys()) == ["name"]


def test_single_dict_input() -> None:
    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update({"json": True, "format": None, "fields": None, "out": None})
        output.render(ctx, {"key": "val"})

    runner = CliRunner()
    result = runner.invoke(cmd)
    parsed = json.loads(result.output)
    assert parsed == [{"key": "val"}]


def test_file_output(tmp_path: Path) -> None:
    out_file = tmp_path / "out.json"

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update(
            {"json": True, "format": None, "fields": None, "out": str(out_file)}
        )
        output.render(ctx, _SAMPLE)

    runner = CliRunner()
    result = runner.invoke(cmd)
    assert out_file.exists()
    parsed = json.loads(out_file.read_text())
    assert len(parsed) == 2
    assert "Written to" in result.stderr


def test_error_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    output.error("something broke")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error: something broke" in captured.err
