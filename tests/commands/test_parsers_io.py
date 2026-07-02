"""Tests for parsers-as-code YAML export/import."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.parsers_io.get_client"


def _configs_resp(content: dict[str, object]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps({"entry": [{"content": content}]}).encode()
    return resp


def _mock_stanza(name: str, app: str = "search") -> MagicMock:
    s = MagicMock()
    s.name = name
    s.access = {"app": app, "sharing": "app"}
    s.content = {}
    return s


@patch(_PATCH)
def test_export_writes_explicit_keys(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = mock_gc.return_value.service
    conf = MagicMock()
    conf.list.return_value = [_mock_stanza("acme:fw")]
    svc.confs.__getitem__.return_value = conf
    svc.get.return_value = _configs_resp(
        {"TIME_FORMAT": "%s", "eai:appName": "search", "disabled": False}
    )

    out = tmp_path / "parsers.yaml"
    result = CliRunner().invoke(
        cli,
        [
            "parsers",
            "export",
            "--path",
            str(out),
            "--conf",
            "props",
            "--filter",
            "acme",
        ],
    )
    assert result.exit_code == 0, result.output
    docs = yaml.safe_load(out.read_text())
    assert docs == [
        {
            "conf": "props",
            "stanza": "acme:fw",
            "app": "search",
            "sharing": "app",
            "keys": {"TIME_FORMAT": "%s"},
        }
    ]


@patch(_PATCH)
def test_import_applies_keys_and_acl(mock_gc: MagicMock, tmp_path: Path) -> None:
    yml = tmp_path / "parsers.yaml"
    yml.write_text(
        yaml.dump(
            [
                {
                    "conf": "props",
                    "stanza": "acme:fw",
                    "sharing": "app",
                    "keys": {"TIME_FORMAT": "%s", "SHOULD_LINEMERGE": "false"},
                }
            ]
        )
    )
    client = mock_gc.return_value
    conf = MagicMock()
    conf.__getitem__.side_effect = KeyError("missing")
    created = MagicMock()
    conf.create.return_value = created
    client.service.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["--yes", "parsers", "import", "--path", str(yml)])
    assert result.exit_code == 0, result.output
    _, kwargs = conf.create.call_args
    assert kwargs == {"TIME_FORMAT": "%s", "SHOULD_LINEMERGE": "false"}
    client.set_acl.assert_called_once_with(created, sharing="app")
    assert "1 created" in result.stderr


@patch(_PATCH)
def test_import_unchanged_is_idempotent(mock_gc: MagicMock, tmp_path: Path) -> None:
    yml = tmp_path / "parsers.yaml"
    yml.write_text(
        yaml.dump(
            [{"conf": "props", "stanza": "acme:fw", "keys": {"TIME_FORMAT": "%s"}}]
        )
    )
    stanza = _mock_stanza("acme:fw")
    stanza.content = {"TIME_FORMAT": "%s"}
    conf = MagicMock()
    conf.__getitem__.return_value = stanza
    mock_gc.return_value.service.confs.__getitem__.return_value = conf

    result = CliRunner().invoke(cli, ["--yes", "parsers", "import", "--path", str(yml)])
    assert result.exit_code == 0
    assert "1 unchanged" in result.stderr
    stanza.update.assert_not_called()


@patch(_PATCH)
def test_import_bad_doc_named_skip_exit1(mock_gc: MagicMock, tmp_path: Path) -> None:
    yml = tmp_path / "parsers.yaml"
    yml.write_text(yaml.dump([{"conf": "props", "keys": {"A": "1"}}]))

    result = CliRunner().invoke(cli, ["--yes", "parsers", "import", "--path", str(yml)])
    assert result.exit_code == 1
    assert "no stanza" in result.stderr
