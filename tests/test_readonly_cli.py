"""Invocation-level refusal happens before configuration or transport work."""

import json

import pytest
from click.testing import CliRunner

from splunkctl.main import cli


@pytest.mark.parametrize(
    "args",
    [
        ["--read-only", "--yes", "indexes", "create", "--name", "fixture"],
        ["indexes", "create", "--name", "fixture", "--yes", "--read-only"],
        ["--read-only", "auth", "login", "--target", "siem"],
        ["--read-only", "auth", "logout"],
    ],
)
def test_refusal(args):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert result.exit_code == 1, result.output
    error = json.loads(result.stderr)["error"]
    assert error["kind"] == "permission"
    assert error["http_status"] is None
    assert error["message"].startswith("read-only:")


def test_preview():
    result = CliRunner().invoke(
        cli, ["--read-only", "indexes", "create", "--name", "fixture"]
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.stderr


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_environment_refusal(monkeypatch, value):
    monkeypatch.setenv("SPLUNKCTL_READ_ONLY", value)
    result = CliRunner().invoke(
        cli, ["--yes", "indexes", "create", "--name", "fixture"]
    )
    assert result.exit_code == 1
    assert "read-only:" in result.stderr


def test_guard_refuses_without_transport(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("client constructed before refusal")

    monkeypatch.setattr("splunkctl.commands.indexes.get_client", unexpected)
    result = CliRunner().invoke(
        cli, ["--read-only", "--yes", "indexes", "create", "--name", "fixture"]
    )
    assert result.exit_code == 1
    assert "read-only:" in result.stderr


@pytest.mark.parametrize("soar", [False, True])
def test_config_init_skips_detection(monkeypatch, tmp_path, soar):
    def unexpected(*args, **kwargs):
        pytest.fail("network autodetection in read-only config init")

    monkeypatch.setattr("splunkctl.commands.config_cmd.detector.probe", unexpected)
    monkeypatch.setattr(
        "splunkctl.commands.config_cmd.detector.siem_idp_issuer", unexpected
    )
    args = [
        "--read-only",
        "config",
        "init",
        "--path",
        str(tmp_path / "config.yaml"),
        "--web-url",
        "https://example.test",
        "--no-verify",
    ]
    if soar:
        args += ["--soar"]
    else:
        args += [
            "--host",
            "example.test",
            "--username",
            "admin",
            "--password",
            "fixture",
        ]
    result = CliRunner().invoke(
        cli, args, input="example.test\n8443\n\n\n\n" if soar else "\n"
    )
    assert result.exit_code == 0, result.output


def test_cli_identity_excludes_arguments_and_resets(monkeypatch):
    from splunkctl.request_context import current

    seen = []
    monkeypatch.setattr(
        cli.commands["info"], "callback", lambda: seen.append(current())
    )
    runner = CliRunner()
    for _ in range(2):
        result = runner.invoke(cli, ["--profile", "fixture", "info"])
        assert result.exit_code == 0, result.output
    assert [ctx.command for ctx in seen] == ["info", "info"]
    assert seen[0].request_id != seen[1].request_id
    assert current() is None
