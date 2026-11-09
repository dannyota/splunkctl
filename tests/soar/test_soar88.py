"""Regression coverage for SOAR 8.8 REST behavior."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.commands.soar.workbook_templates import resolve_template
from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


def test_template_filters() -> None:
    client = MagicMock()
    client.get.return_value = {"data": [{"id": 12, "name": 'a"b'}]}
    assert resolve_template(client, 'a"b') == 12
    client.get.assert_called_with(
        "workbook_template", params={"_filter_name": '"a\\"b"'}
    )
    client.get.return_value = {"data": [{"id": 1, "is_default": True}]}
    assert resolve_template(client, None) == 1
    client.get.assert_called_with(
        "workbook_template", params={"_filter_is_default": "True"}
    )
    client.reset_mock()
    assert resolve_template(client, "999") == 999
    client.get.assert_not_called()


@pytest.mark.parametrize("csv_format", [False, True])
@pytest.mark.parametrize("ending", ["short", "empty", "repeat", "oversize", "limit"])
def test_audit_pages(csv_format: bool, ending: str) -> None:
    first = [{"id": i} for i in range(100)]
    second = [{"id": 100}]
    if ending == "empty":
        second = []
    elif ending == "repeat":
        second = first
    elif ending == "oversize":
        first = [{"id": i} for i in range(101)]
    elif ending == "limit":
        second = [{"id": i} for i in range(100, 200)]
    pages = [first, second]
    client = MagicMock()
    if csv_format:
        client.get_bytes.side_effect = [
            ("ID\n" + "".join(f"{row['id']}\n" for row in page)).encode()
            for page in pages
        ]
    else:
        client.get.side_effect = [{"num_pages": 1, "data": page} for page in pages]
    args = ["--json", "soar", "audit"]
    if csv_format:
        args += ["--format", "csv"]
    if ending == "limit":
        args += ["--limit", "101"]
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    method = client.get_bytes if csv_format else client.get
    assert [call.kwargs["params"]["page"] for call in method.call_args_list] == (
        [1] if ending == "oversize" else [1, 2]
    )
    expected = 100 if ending in ("empty", "repeat") else 101
    if csv_format:
        assert result.stdout.splitlines()[0] == "ID"
        assert len(result.stdout.splitlines()) == expected + 1
    else:
        assert len(json.loads(result.stdout)) == expected


def test_playbooks_list_name_and_limit() -> None:
    client = MagicMock()
    client.get.side_effect = [{"data": [{"id": 1}]}, {"data": [{"id": 7}]}]
    name = 'dir/module"quoted'
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "playbooks",
                "list",
                "--repo",
                "local",
                "--name",
                name,
                "--limit",
                "101",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"id": 7}]
    client.get.assert_called_with(
        "playbook",
        params={"_filter_scm": "1", "_filter_name": json.dumps(name), "page_size": 101},
    )


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_playbooks_list_invalid_limit(limit: str) -> None:
    result = CliRunner().invoke(cli, ["soar", "playbooks", "list", "--limit", limit])
    assert result.exit_code == 2
    assert "range" in result.output


@pytest.mark.parametrize("fail", [False, True])
def test_evidence_types(fail: bool) -> None:
    rows = [{"id": i, "content_type": 22 + i} for i in range(3)]
    client = MagicMock()
    client.get.side_effect = [{"data": rows}] + (
        [SOARError("unsupported", kind="http")] * 3
        if fail
        else [{"data": [row]} for row in rows]
    )
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli, ["--json", "soar", "evidence", "list", "--container", "7"]
        )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert [r["content_type"] for r in data] == [22, 23, 24]
    if fail:
        assert all("object_type" not in r for r in data)
        assert result.stderr.count("Could not resolve") == 1
    else:
        assert [r["object_type"] for r in data] == ["artifact", "note", "action_run"]
    for call, model in zip(
        client.get.call_args_list[1:], ["artifact", "note", "actionrun"], strict=True
    ):
        assert call.kwargs["params"]["_filter_content_type__model"] == json.dumps(model)
        assert call.kwargs["params"]["_filter_container"] == 7


@pytest.mark.parametrize("fail", [False, True])
def test_vault_hashes(fail: bool) -> None:
    client = MagicMock()
    client.get.side_effect = [
        {"data": [{"id": 1, "vault_document": 2}, {"id": 3, "vault_document": 2}]},
        SOARError("unsupported", kind="http")
        if fail
        else {"data": [{"id": 2, "hash": "sha1"}]},
    ]
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(cli, ["--json", "soar", "vault", "list"])
    assert result.exit_code == 0
    client.get.assert_called_with(
        "vault_document", params={"_filter_id__in": "[2]", "page_size": 1}
    )
    assert [r.get("vault_id") for r in json.loads(result.stdout)] == (
        [None, None] if fail else ["sha1", "sha1"]
    )


@pytest.mark.parametrize(
    "verb,extra",
    [("enable", []), ("disable", []), ("trigger", ["--on", "artifact_created"])],
)
def test_previous_playbook_hint(verb: str, extra: list[str]) -> None:
    client = MagicMock()
    client.post.side_effect = SOARError(
        "No Playbook matches", kind="http", http_status=404
    )
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli, ["soar", "playbooks", verb, "1", *extra, "--yes"]
        )
    assert result.exit_code == 1
    assert "read-only previous version" in result.stderr
    assert "soar playbooks list" in result.stderr


@pytest.mark.parametrize("reject", [False, True])
def test_function_python_override(tmp_path, reject: bool) -> None:
    source = tmp_path / "function.py"
    source.write_text("def f(): pass\n")
    client = MagicMock()
    client.get.side_effect = [{"data": [{"id": 1}]}, {"python_version": "3.9"}]
    client.post.return_value = {"id": 1}
    if reject:
        client.post.side_effect = SOARError(
            "Editing Python 3.9 custom functions is not supported", kind="http"
        )
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "soar",
                "functions",
                "update",
                "1",
                "--python",
                str(source),
                "--message",
                "update",
                "--python-version",
                "3.13",
                "--yes",
            ],
        )
    assert result.exit_code == int(reject)
    assert client.post.call_args.kwargs["body"]["python_version"] == "3.13"
    if reject:
        assert "--python-version 3.13" in result.stderr


def test_function_draft_warning(tmp_path) -> None:
    archive = tmp_path / "function.tgz"
    archive.write_bytes(b"archive")
    client = MagicMock()
    client.post.return_value = {
        "id": 1,
        "message": "Failed validation. Custom Function saved as draft.",
    }
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli, ["soar", "functions", "import", str(archive), "--yes"]
        )
    assert result.exit_code == 0
    assert "saved as draft" in result.stderr


@pytest.mark.parametrize("csv_format", [False, True])
def test_audit_empty(csv_format: bool) -> None:
    client = MagicMock()
    client.get.return_value = {"data": []}
    client.get_bytes.return_value = b""
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
    ):
        result = CliRunner().invoke(
            cli,
            ["--json", "soar", "audit"] + (["--format", "csv"] if csv_format else []),
        )
    assert result.exit_code == 0
    assert result.stdout == ("" if csv_format else "[]\n")
