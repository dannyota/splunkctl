"""Tests for kvstore document CRUD (data API): insert/update/remove/export/import.

Also covers the F1 error-envelope classification for a down KV store, and
the guard markers ``commands --json`` exposes for the whole group.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.kvstore.get_client"


def _resp(body: object) -> MagicMock:
    r = MagicMock()
    if isinstance(body, (bytes, bytearray)):
        r.body.read.return_value = body
    else:
        r.body.read.return_value = json.dumps(body).encode()
    return r


def _http_error(status: int, reason: str, msg: str) -> Exception:
    """Build a real splunklib HTTPError, matching what a live KV-store-down
    call actually raises (so errors.classify's name-based check applies)."""
    from splunklib.binding import HTTPError

    xml_body = (
        f'<response><messages><msg type="ERROR">{msg}</msg></messages></response>'
    ).encode()
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    resp.body.read.return_value = xml_body
    resp.headers = []
    return HTTPError(resp)


# --- insert ---


@patch(_PATCH)
def test_insert_dry_run_no_call(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "insert", "agenttest_g3", "--data", '{"host": "x"}']
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    mock_gc.return_value.service.post.assert_not_called()


@patch(_PATCH)
def test_insert_with_data_applies(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp({"_key": "abc123"})

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "kvstore",
            "insert",
            "agenttest_g3",
            "--data",
            '{"host": "evil.example"}',
        ],
    )
    assert result.exit_code == 0
    assert "abc123" in result.stderr
    svc.post.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        headers=[("Content-Type", "application/json")],
        body=json.dumps({"host": "evil.example"}),
    )


@patch(_PATCH)
def test_insert_with_file_applies(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp({"_key": "abc123"})
    doc_file = tmp_path / "doc.json"
    doc_file.write_text('{"host": "evil.example"}')

    result = CliRunner().invoke(
        cli,
        ["--yes", "kvstore", "insert", "agenttest_g3", "--file", str(doc_file)],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        headers=[("Content-Type", "application/json")],
        body=json.dumps({"host": "evil.example"}),
    )


def test_insert_requires_exactly_one_of_data_or_file() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "insert", "agenttest_g3"])
    assert result.exit_code == 2


def test_insert_rejects_both_data_and_file(tmp_path: Path) -> None:
    doc_file = tmp_path / "doc.json"
    doc_file.write_text("{}")
    result = CliRunner().invoke(
        cli,
        [
            "kvstore",
            "insert",
            "agenttest_g3",
            "--data",
            "{}",
            "--file",
            str(doc_file),
        ],
    )
    assert result.exit_code == 2


def test_insert_invalid_json_is_usage_error() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "insert", "agenttest_g3", "--data", "{not json"]
    )
    assert result.exit_code == 2


def test_insert_rejects_non_object_json() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "insert", "agenttest_g3", "--data", "[1, 2, 3]"]
    )
    assert result.exit_code == 2


# --- update ---


@patch(_PATCH)
def test_update_applies(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp({"_key": "k1"})

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "kvstore",
            "update",
            "agenttest_g3",
            "k1",
            "--data",
            '{"host": "new.example"}',
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once_with(
        "storage/collections/data/agenttest_g3/k1",
        owner="nobody",
        app="search",
        headers=[("Content-Type", "application/json")],
        body=json.dumps({"host": "new.example"}),
    )


def test_update_dry_run_no_call() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "update", "agenttest_g3", "k1", "--data", "{}"]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


def test_update_requires_exactly_one_of_data_or_file() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "update", "agenttest_g3", "k1"])
    assert result.exit_code == 2


# --- remove ---


@patch(_PATCH)
def test_remove_by_key_applies(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(
        cli, ["--yes", "kvstore", "remove", "agenttest_g3", "k1"]
    )
    assert result.exit_code == 0
    svc.delete.assert_called_once_with(
        "storage/collections/data/agenttest_g3/k1", owner="nobody", app="search"
    )


@patch(_PATCH)
def test_remove_by_query_applies(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "kvstore",
            "remove",
            "agenttest_g3",
            "--query",
            '{"host": "evil.example"}',
        ],
    )
    assert result.exit_code == 0
    svc.delete.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        query='{"host": "evil.example"}',
    )


def test_remove_requires_exactly_one_of_key_or_query() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "remove", "agenttest_g3"])
    assert result.exit_code == 2


def test_remove_rejects_both_key_and_query() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "remove", "agenttest_g3", "k1", "--query", "{}"]
    )
    assert result.exit_code == 2


def test_remove_invalid_query_json_is_usage_error() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "remove", "agenttest_g3", "--query", "{not json"]
    )
    assert result.exit_code == 2


def test_remove_by_key_dry_run_no_call() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "remove", "agenttest_g3", "k1"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr


# --- export ---


@patch(_PATCH)
def test_export_writes_jsonl_to_stdout(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    docs = [{"_key": "k1", "host": "a"}, {"_key": "k2", "host": "b"}]
    svc.get.return_value = _resp(docs)

    result = CliRunner().invoke(cli, ["kvstore", "export", "agenttest_g3"])
    assert result.exit_code == 0
    lines = result.stdout.strip("\n").splitlines()
    assert [json.loads(line) for line in lines] == docs
    svc.get.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        output_mode="json",
    )


@patch(_PATCH)
def test_export_to_out_file(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = mock_gc.return_value.service
    docs = [{"_key": "k1", "host": "a"}]
    svc.get.return_value = _resp(docs)
    out_file = tmp_path / "out.jsonl"

    result = CliRunner().invoke(
        cli, ["kvstore", "export", "agenttest_g3", "--out", str(out_file)]
    )
    assert result.exit_code == 0
    lines = out_file.read_text().strip("\n").splitlines()
    assert [json.loads(line) for line in lines] == docs


@patch(_PATCH)
def test_export_empty_collection(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp([])

    result = CliRunner().invoke(cli, ["kvstore", "export", "agenttest_g3"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Exported 0 document(s)" in result.stderr


# --- import ---


@patch(_PATCH)
def test_import_applies_single_batch(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp(["k1", "k2"])
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text('{"_key": "k1", "host": "a"}\n{"_key": "k2", "host": "b"}\n')

    result = CliRunner().invoke(
        cli, ["--yes", "kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 0
    assert "2 document" in result.stderr
    svc.post.assert_called_once_with(
        "storage/collections/data/agenttest_g3/batch_save",
        owner="nobody",
        app="search",
        headers=[("Content-Type", "application/json")],
        body=json.dumps([{"_key": "k1", "host": "a"}, {"_key": "k2", "host": "b"}]),
    )


@patch(_PATCH)
def test_import_chunks_at_500(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp([])
    docs = [{"_key": f"k{i}"} for i in range(501)]
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text("\n".join(json.dumps(d) for d in docs) + "\n")

    result = CliRunner().invoke(
        cli, ["--yes", "kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 0
    assert svc.post.call_count == 2
    first_body = json.loads(svc.post.call_args_list[0].kwargs["body"])
    second_body = json.loads(svc.post.call_args_list[1].kwargs["body"])
    assert len(first_body) == 500
    assert len(second_body) == 1
    assert first_body == docs[:500]
    assert second_body == docs[500:]


def test_import_missing_file_is_usage_error() -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "import", "agenttest_g3", "--file", "/nonexistent.jsonl"]
    )
    # missing file is a click.Path(exists=True) usage error, exit 2
    assert result.exit_code == 2


@patch(_PATCH)
def test_import_dry_run_no_call(mock_gc: MagicMock, tmp_path: Path) -> None:
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text('{"a": 1}\n')

    result = CliRunner().invoke(
        cli, ["kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "1 document" in result.stderr
    mock_gc.return_value.service.post.assert_not_called()


def test_import_invalid_json_line_is_usage_error(tmp_path: Path) -> None:
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text("{not json}\n")

    result = CliRunner().invoke(
        cli, ["kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 2


def test_import_rejects_non_object_line(tmp_path: Path) -> None:
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text("[1, 2, 3]\n")

    result = CliRunner().invoke(
        cli, ["kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 2


def test_import_skips_blank_lines(tmp_path: Path) -> None:
    jsonl = tmp_path / "docs.jsonl"
    jsonl.write_text('{"a": 1}\n\n   \n{"b": 2}\n')

    result = CliRunner().invoke(
        cli, ["kvstore", "import", "agenttest_g3", "--file", str(jsonl)]
    )
    assert result.exit_code == 0
    assert "2 document" in result.stderr


# --- F1 envelope classification: a down KV store never returns blank/traceback ---


@patch(_PATCH)
def test_query_kv_store_down_classified_envelope(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(
        503,
        "Service Unavailable",
        "KV Store initialization failed. Please contact your system administrator.",
    )

    result = CliRunner().invoke(cli, ["--json", "kvstore", "query", "agenttest_g3"])
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "http"
    assert payload["error"]["http_status"] == 503
    assert "KV Store initialization failed" in payload["error"]["message"]
    # never a bare traceback
    assert "Traceback" not in result.output
    assert "Traceback" not in result.stderr


@patch(_PATCH)
def test_create_kv_store_down_classified_envelope(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.side_effect = _http_error(
        503,
        "Service Unavailable",
        "KV Store initialization failed. Please contact your system administrator.",
    )

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "kvstore", "create", "agenttest_g3"]
    )
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["error"]["kind"] == "http"
    assert payload["error"]["http_status"] == 503


# --- commands --json exposes guard markers ---


def test_commands_json_includes_kvstore_guard_markers() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.output)
    kv = next(c for c in tree["commands"] if c["name"] == "kvstore")
    guarded = {c["name"] for c in kv["subcommands"] if c.get("guarded")}
    assert guarded == {"create", "delete", "insert", "update", "remove", "import"}
    unguarded = {c["name"] for c in kv["subcommands"] if not c.get("guarded")}
    assert unguarded == {"collections", "query", "export"}
