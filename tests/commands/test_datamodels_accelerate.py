"""Guarded acceleration configuration through the shared conf writer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.datamodels.get_client"


def _configure(client: MagicMock) -> tuple[MagicMock, MagicMock]:
    response = MagicMock()
    response.body.read.return_value = json.dumps(
        {
            "entry": [
                {
                    "name": "Authentication",
                    "acl": {"app": "Splunk_SA_CIM"},
                    "content": {"acceleration": '{"enabled": false}'},
                }
            ]
        }
    ).encode()
    client.service.get.return_value = response
    conf = client.service.confs.__getitem__.return_value
    stanza = conf.__getitem__.return_value
    stanza.content = {
        "acceleration": "false",
        "acceleration.earliest_time": "-7d",
        "acceleration.cron_schedule": "0 * * * *",
    }
    return conf, stanza


@patch(_PATCH)
def test_accelerate_previews_exact_changes_without_writing(mock_gc: MagicMock) -> None:
    client = mock_gc.return_value
    conf, stanza = _configure(client)
    result = CliRunner().invoke(cli, ["datamodels", "accelerate", "authentication"])

    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.stderr
    assert "Splunk_SA_CIM" in result.stderr
    assert "datamodels.conf" in result.stderr
    assert "Authentication" in result.stderr
    assert "acceleration: false -> true" in result.stderr
    assert "acceleration.earliest_time: -7d -> -1mon" in result.stderr
    assert "acceleration.cron_schedule: 0 * * * * -> */5 * * * *" in result.stderr
    stanza.update.assert_not_called()
    conf.create.assert_not_called()
    client.service.post.assert_not_called()


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (
            [],
            {
                "acceleration": "true",
                "acceleration.earliest_time": "-1mon",
                "acceleration.cron_schedule": "*/5 * * * *",
            },
        ),
        (
            ["--earliest", "-15m", "--cron", "0 * * * *"],
            {
                "acceleration": "true",
                "acceleration.earliest_time": "-15m",
                "acceleration.cron_schedule": "0 * * * *",
            },
        ),
        (
            ["--disable"],
            {
                "acceleration": "false",
                "acceleration.earliest_time": "-1mon",
                "acceleration.cron_schedule": "*/5 * * * *",
            },
        ),
    ],
)
@patch(_PATCH)
def test_accelerate_updates_resolved_app_and_canonical_model(
    mock_gc: MagicMock, options: list[str], expected: dict[str, str]
) -> None:
    client = mock_gc.return_value
    conf, stanza = _configure(client)
    result = CliRunner().invoke(
        cli,
        ["datamodels", "accelerate", "authentication", "--app", "Splunk_SA_CIM"]
        + options
        + ["--yes"],
    )

    assert result.exit_code == 0, result.output
    client.service.confs.__getitem__.assert_called_with("datamodels")
    for lookup in conf.__getitem__.call_args_list:
        name, namespace = lookup.args[0]
        assert (name, namespace.owner, namespace.app) == (
            "Authentication",
            "-",
            "Splunk_SA_CIM",
        )
    assert client.service.get.call_args.kwargs["app"] == "Splunk_SA_CIM"
    stanza.update.assert_called_once_with(**expected)
    conf.create.assert_not_called()
    client.service.post.assert_not_called()


@patch(_PATCH)
def test_accelerate_creates_missing_configuration_in_model_app(
    mock_gc: MagicMock,
) -> None:
    client = mock_gc.return_value
    conf, _ = _configure(client)
    conf.__getitem__.side_effect = KeyError("Authentication")
    result = CliRunner().invoke(
        cli, ["datamodels", "accelerate", "Authentication", "--yes"]
    )

    assert result.exit_code == 0, result.output
    conf.create.assert_called_once_with(
        "Authentication",
        app="Splunk_SA_CIM",
        acceleration="true",
        **{
            "acceleration.earliest_time": "-1mon",
            "acceleration.cron_schedule": "*/5 * * * *",
        },
    )
    client.set_acl.assert_called_once_with(conf.create.return_value, sharing="app")


@patch(_PATCH)
def test_accelerate_missing_model_never_creates_configuration(
    mock_gc: MagicMock,
) -> None:
    client = mock_gc.return_value
    _configure(client)
    client.service.get.return_value.body.read.return_value = b'{"entry": []}'
    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "accelerate", "missing", "--yes"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["kind"] == "not_found"
    client.service.confs.__getitem__.assert_not_called()
