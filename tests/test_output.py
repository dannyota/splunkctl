"""Tests for splunkctl.output."""

import json
import sys
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


def _error_cmd(
    msg: str,
    *,
    kind: str | None = None,
    http_status: int | None = None,
    **flags: object,
) -> click.Command:
    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update({"json": False, "format": None, **flags})
        if kind is None:
            output.error(msg)
        else:
            output.error(msg, kind=kind, http_status=http_status)

    return cmd


def test_error_envelope_under_json_flag() -> None:
    result = CliRunner().invoke(
        _error_cmd("not found: rule1", kind="not_found", http_status=404, json=True)
    )
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload == {
        "error": {
            "kind": "not_found",
            "http_status": 404,
            "message": "not found: rule1",
        }
    }


def test_error_envelope_under_format_json() -> None:
    result = CliRunner().invoke(
        _error_cmd("bad token", kind="permission", http_status=403, format="json")
    )
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "permission"
    assert payload["error"]["http_status"] == 403


def test_error_envelope_is_single_line() -> None:
    result = CliRunner().invoke(
        _error_cmd("boom", kind="http", http_status=500, json=True)
    )
    assert result.stderr.strip().count("\n") == 0


def test_error_human_text_unchanged_for_table_format() -> None:
    result = CliRunner().invoke(
        _error_cmd("rule1 missing", kind="not_found", http_status=404, format="table")
    )
    assert result.stderr == "Error: rule1 missing\n"


def test_error_envelope_when_piped_no_format_flags() -> None:
    """No format flags + non-tty stdout (CliRunner's default) resolves to
    JSON, mirroring the data-rendering piped default — an agent piping
    splunkctl without ``--json`` still gets a `jq`-able error envelope."""
    result = CliRunner().invoke(
        _error_cmd("rule1 missing", kind="not_found", http_status=404)
    )
    payload = json.loads(result.stderr)
    assert payload == {
        "error": {"kind": "not_found", "http_status": 404, "message": "rule1 missing"}
    }


def test_error_human_text_when_tty_no_format_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real tty with no format flags keeps human error text — only the
    piped default resolves to JSON."""

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        ctx.ensure_object(dict)
        ctx.obj.update({"json": False, "format": None})
        output.error("rule1 missing", kind="not_found", http_status=404)

    result = CliRunner().invoke(cmd)
    assert result.stderr == "Error: rule1 missing\n"


def test_error_human_text_unchanged_for_csv_format() -> None:
    result = CliRunner().invoke(
        _error_cmd("rule1 missing", kind="not_found", http_status=404, format="csv")
    )
    assert result.stderr == "Error: rule1 missing\n"


def test_error_default_kind_is_error_fallback() -> None:
    result = CliRunner().invoke(_error_cmd("unclassified failure", json=True))
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "error"
    assert payload["error"]["http_status"] is None


def test_error_http_status_null_for_non_http_kind() -> None:
    result = CliRunner().invoke(
        _error_cmd("socket refused", kind="connection", json=True)
    )
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "connection"
    assert payload["error"]["http_status"] is None


def test_error_message_strips_error_prefix() -> None:
    result = CliRunner().invoke(
        _error_cmd("Saved search not found: foo", kind="not_found", json=True)
    )
    payload = json.loads(result.stderr)
    assert payload["error"]["message"] == "Saved search not found: foo"
    assert not payload["error"]["message"].startswith("Error: ")


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
