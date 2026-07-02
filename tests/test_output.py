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


def _render_cmd(
    data: list[dict[str, object]], *, empty: str | None = None, **flags: object
) -> click.Command:
    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update(
            {"json": False, "format": None, "fields": None, "out": None, **flags}
        )
        output.render(ctx, data, empty=empty)

    return cmd


def test_csv_sparse_columns_union() -> None:
    rows: list[dict[str, object]] = [{"a": 1}, {"a": 2, "b": 3}]
    result = CliRunner().invoke(_render_cmd(rows, format="csv"))
    lines = result.output.strip().split("\n")
    assert lines[0] == "a,b"
    assert lines[1] == "1,"
    assert lines[2] == "2,3"


def test_json_empty_list_stdout() -> None:
    result = CliRunner().invoke(_render_cmd([], format="json"))
    assert result.stdout.strip() == "[]"


def test_piped_default_empty_is_json_list() -> None:
    result = CliRunner().invoke(_render_cmd([]))
    assert result.stdout.strip() == "[]"


def test_jsonl_empty_no_stdout() -> None:
    result = CliRunner().invoke(_render_cmd([], format="jsonl"))
    assert result.stdout == ""


def test_csv_empty_no_stdout() -> None:
    result = CliRunner().invoke(_render_cmd([], format="csv"))
    assert result.stdout == ""


def test_table_empty_message_stderr() -> None:
    result = CliRunner().invoke(
        _render_cmd([], empty="No widgets found.", format="table")
    )
    assert result.stdout == ""
    assert "No widgets found." in result.stderr


def test_is_table_resolution() -> None:
    @click.command()
    @click.option("--fmt", default=None)
    @click.option("--use-json", is_flag=True)
    @click.pass_context
    def cmd(ctx: click.Context, fmt: str | None, use_json: bool) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update({"json": use_json, "format": fmt})
        click.echo(str(output.is_table(ctx)))

    runner = CliRunner()
    assert runner.invoke(cmd, ["--fmt", "table"]).output.strip() == "True"
    assert runner.invoke(cmd, ["--fmt", "csv"]).output.strip() == "False"
    assert runner.invoke(cmd, ["--use-json"]).output.strip() == "False"
    # piped (non-TTY) with no flags resolves to JSON, not table
    assert runner.invoke(cmd, []).output.strip() == "False"
