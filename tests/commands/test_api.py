"""Raw API validation and wire contracts."""

import io
import json
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from splunkctl.api_paths import validate_path
from splunkctl.commands.api import api_group


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.test/x",
        "//evil.test/x",
        "x\\y",
        "x\ny",
        "x?y=1",
        "x#y",
        "../x",
        "x/./y",
        "x/%2f/y",
        "x/%5c/y",
        "x/%252e%252e/y",
        "x/%25252f/y",
        "x/%00/y",
        "/arbitrary/x",
        "x/%GG",
        "x//y",
    ],
)
def test_path_attacks(path: str) -> None:
    with pytest.raises(click.BadParameter):
        validate_path(path)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("server/info", "/services/server/info"),
        (
            "saved/searches/name%20with%20spaces",
            "/services/saved/searches/name%20with%20spaces",
        ),
        ("saved/searches/name:colon", "/services/saved/searches/name:colon"),
        ("/services/server/info", "/services/server/info"),
        (
            "/servicesNS/nobody/search/saved/searches",
            "/servicesNS/nobody/search/saved/searches",
        ),
    ],
)
def test_paths(path: str, expected: str) -> None:
    assert validate_path(path) == expected


def invoke(args: list[str], data: object = None, obj: dict | None = None):
    svc = MagicMock()
    svc.post.return_value.body = svc.request.return_value.body = io.BytesIO(
        json.dumps(data).encode() if data is not None else b""
    )
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = svc
        result = CliRunner().invoke(api_group, args, obj=obj or {})
    return result, svc


def test_get_preserves_envelope_and_duplicates() -> None:
    result, svc = invoke(
        ["get", "server/info", "--param", "f=a", "--param", "f=b"], {"entry": []}
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"entry": []}]
    assert (
        str(svc.request.call_args.args[0])
        == "/services/server/info?f=a&f=b&output_mode=json"
    )


def test_preview_never_constructs_client() -> None:
    with patch("splunkctl.commands.api.get_client") as client:
        result = CliRunner().invoke(
            api_group, ["post", "saved/searches", "--param", "name=example"]
        )
    assert result.exit_code == 0
    client.assert_not_called()


def test_form_and_raw_body() -> None:
    result, svc = invoke(
        [
            "post",
            "saved/searches",
            "--param",
            "name=a",
            "--param",
            "f=a",
            "--param",
            "f=b",
        ],
        obj={"dry_run": False},
    )
    assert result.exit_code == 0, result.output
    assert svc.post.call_args.kwargs["body"] == b"name=a&f=a&f=b"
    result, svc = invoke(
        [
            "post",
            "storage/collections/data/test",
            "--body",
            '{"a":1}',
            "--param",
            "x=y",
            "--content-type",
            "application/json",
        ],
        obj={"dry_run": False},
    )
    assert result.exit_code == 0, result.output
    assert svc.post.call_args.kwargs["body"] == b'{"a":1}'
    assert str(svc.post.call_args.args[0]).endswith("?x=y&output_mode=json")


def test_delete_empty() -> None:
    result, svc = invoke(["delete", "saved/searches/example"], obj={"dry_run": False})
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    assert svc.request.call_args.kwargs["method"] == "DELETE"


@pytest.mark.parametrize(
    "args",
    [
        ["get", "server/info", "--param", "output_mode=xml"],
        ["get", "server/info", "--param", "bad"],
        ["post", "server/info", "--body", "x", "--body-file", "missing"],
    ],
)
def test_invalid_options_before_client(args: list[str]) -> None:
    with patch("splunkctl.commands.api.get_client") as client:
        result = CliRunner().invoke(api_group, args)
    assert result.exit_code == 2
    client.assert_not_called()


def test_describe() -> None:
    data = {
        "entry": [
            {
                "fields": {
                    "required": ["name", "search"],
                    "optional": ["description"],
                    "wildcard": ["action\\..*"],
                }
            }
        ]
    }
    result, svc = invoke(["get", "saved/searches", "--describe"], data)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [
        {"field": "name", "kind": "required"},
        {"field": "search", "kind": "required"},
        {"field": "description", "kind": "optional"},
        {"field": "action\\..*", "kind": "wildcard"},
    ]
    assert str(svc.request.call_args.args[0]).startswith(
        "/services/saved/searches/_new?"
    )


def test_unsupported_describe() -> None:
    result, _ = invoke(
        ["get", "server/info", "--describe"], {"entry": [{"content": {}}]}
    )
    assert result.exit_code != 0
    assert "discovery" in str(result.exception)


def test_body_file_and_projection(tmp_path) -> None:
    body_file = tmp_path / "body.json"
    body_file.write_text('{"record":2}')
    result, svc = invoke(
        ["post", "storage/collections/data/example", "--body-file", str(body_file)],
        {"a": 1, "b": 2},
        obj={"dry_run": False, "fields": "a", "out": str(tmp_path / "out.json")},
    )
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "out.json").read_text()) == [{"a": 1}]
    assert svc.post.call_args.kwargs["body"] == b'{"record":2}'


def test_actual_sdk_wire_encoding() -> None:
    """Exercise SDK URL assembly, not a mock's interpretation of parameters."""
    from splunklib.binding import Context

    seen = []

    def handler(url, message, **kwargs):
        seen.append((str(url), message))
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(b"{}")}

    service = Context(host="example.test", token="test-token", handler=handler)  # noqa: S106
    with patch("splunkctl.commands.api.get_client") as client:
        client.return_value.service = service
        result = CliRunner().invoke(
            api_group,
            [
                "post",
                "saved/searches",
                "--param",
                "name=a b",
                "--param",
                "f=a",
                "--param",
                "f=b",
            ],
            obj={"dry_run": False},
        )
    assert result.exit_code == 0, result.output
    assert (
        seen[0][0]
        == "https://example.test:8089/services/saved/searches?output_mode=json"
    )
    assert seen[0][1]["body"] == b"name=a+b&f=a&f=b"


@pytest.mark.parametrize(
    "path", ["services/server/info", "servicesNS/nobody/search/server/info"]
)
def test_prefix_without_slash(path):
    result, svc = invoke(["get", path], {})
    assert result.exit_code == 0, result.output
    assert str(svc.request.call_args.args[0]).startswith("/" + path + "?")
