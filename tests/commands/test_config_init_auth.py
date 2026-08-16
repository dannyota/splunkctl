from unittest.mock import patch

from click.testing import CliRunner

from splunkctl import config as cfg_mod
from splunkctl.main import cli


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="browser")
def test_init_detects_saml_and_saves_browser_mode(mock_probe) -> None:
    args = (
        "config init --host 100.65.1.10 --port 8089 --username admin "
        "--password pw --verify --web-url http://100.65.1.10:8000 "
        f"--path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    cfg = cfg_mod.load(cfg_mod.DEFAULT_PATH)
    assert cfg["auth_mode"] == "browser"
    assert cfg["web_url"] == "http://100.65.1.10:8000"


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="password")
def test_init_saves_password_mode_when_no_saml(mock_probe) -> None:
    args = (
        "config init --host 100.65.1.10 --port 8089 --username admin "
        "--password pw --verify --web-url http://100.65.1.10:8000 "
        f"--path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    cfg = cfg_mod.load(cfg_mod.DEFAULT_PATH)
    assert cfg["auth_mode"] == "password"


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="browser")
def test_init_soar_probes_with_collected_verify(mock_probe) -> None:
    args = (
        f"config init --soar --web-url https://soar:8443 --path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args, input="soar-host\n8443\n\n\n\nn\n\n")
    assert result.exit_code == 0, result.output
    assert mock_probe.call_args.kwargs["verify"] is False
    assert cfg_mod.resolve_soar(cfg_mod.DEFAULT_PATH)["verify"] is False


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="browser")
def test_init_soar_no_verify_flag_skips_prompt(mock_probe) -> None:
    args = (
        f"config init --soar --no-verify --web-url https://soar:8443 "
        f"--path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args, input="soar-host\n8443\n\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert cfg_mod.resolve_soar(cfg_mod.DEFAULT_PATH)["verify"] is False


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="browser")
def test_init_soar_sso_url_is_stored_and_probed(mock_probe) -> None:
    sso = "https://soar:8443/saml2/login?idp=https://idp&next=/"
    args = (
        "config init --soar --no-verify --web-url https://soar:8443 "
        f"--sso-url {sso} --path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args, input="soar-host\n8443\n\n\n\n")
    assert result.exit_code == 0, result.output
    cfg = cfg_mod.resolve_soar(cfg_mod.DEFAULT_PATH)
    assert cfg["sso_url"] == sso
    assert mock_probe.call_args.args[0] == sso


@patch("splunkctl.commands.config_cmd.detector.probe", return_value="browser")
@patch(
    "splunkctl.commands.config_cmd.detector.siem_idp_issuer",
    return_value="http://idp:8080/realms/splunklab",
)
def test_init_soar_derives_sso_url_from_siem(mock_issuer, mock_probe) -> None:
    # A browser-authenticated SIEM in the same profile supplies the IdP issuer.
    cfg_mod.save(
        {
            "host": "100.65.1.10",
            "web_url": "http://100.65.1.10:8000",
            "auth_mode": "browser",
        },
        cfg_mod.DEFAULT_PATH,
    )
    args = (
        "config init --soar --no-verify --web-url https://soar:8443 "
        f"--path {cfg_mod.DEFAULT_PATH}"
    ).split()
    result = CliRunner().invoke(cli, args, input="soar-host\n8443\n\n\n\n")
    assert result.exit_code == 0, result.output
    cfg = cfg_mod.resolve_soar(cfg_mod.DEFAULT_PATH)
    assert cfg["sso_url"] == (
        "https://soar-host:8443/saml2/login?idp=http://idp:8080/realms/splunklab&next=/"
    )
    mock_issuer.assert_called_once_with(
        "http://100.65.1.10:8000", verify=True, timeout=30
    )
