"""TLS settings must reach both HTTP clients."""

from pathlib import Path
from unittest.mock import patch

import pytest

from splunkctl.client import SplunkClient
from splunkctl.soar.client import SOARClient
from splunkctl.soar.web import ensure_web_login


@pytest.mark.parametrize("verify", [None, True, False])
def test_siem_explicit_verify(
    verify: bool | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("host: example\nport: 8089\ntoken: secret\n")
    with (
        patch("splunkctl.client.splunk_client.connect") as connect,
        patch("splunkctl.client._tls_warned", False),
    ):
        _ = SplunkClient(config_path=config, verify=verify).service
    assert connect.call_args.kwargs["verify"] is (verify is not False)
    assert ("TLS certificate verification is disabled" in capsys.readouterr().err) is (
        verify is False
    )


def test_soar_default_verifies_api_and_web() -> None:
    client = SOARClient(host="example", cookies={"csrftoken": "secret"})
    assert client._session.verify is True
    assert ensure_web_login(client).verify is True


def test_soar_explicit_disable_reaches_web() -> None:
    client = SOARClient(host="example", verify=False, cookies={"csrftoken": "secret"})
    assert client._session.verify is False
    assert ensure_web_login(client).verify is False
