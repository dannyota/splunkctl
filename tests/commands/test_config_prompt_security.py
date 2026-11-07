"""SOAR token prompts must conceal credentials."""

from pathlib import Path
from unittest.mock import patch

from splunkctl.commands.config_cmd import _init_soar


def test_soar_token_prompt_hidden(tmp_path: Path) -> None:
    with patch(
        "splunkctl.commands.config_cmd.click.prompt",
        side_effect=["example", 8443, "secret", "", ""],
    ) as prompt:
        _init_soar(
            dest=tmp_path / "config.yaml",
            profile_name=None,
            auth_mode="token",
            sso_url="https://example/login",
            web_url=None,
            verify=True,
        )
    token_call = next(c for c in prompt.call_args_list if c.args[0] == "SOAR token")
    assert token_call.kwargs["hide_input"] is True
