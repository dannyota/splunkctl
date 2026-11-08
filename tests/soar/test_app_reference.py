"""Asset app names must resolve before asset writes and action submission."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg


@pytest.mark.parametrize("reference", [5, "5", "DNS", "missing", "duplicate"])
@pytest.mark.parametrize("command", ["assets", "actions"])
def test_app_reference(reference: int | str, command: str) -> None:
    client = MagicMock()
    asset = {"name": "fixture", "app": reference, "configuration": {"keep": "value"}}

    def get(path: str, **kwargs: object) -> dict:
        if path == "asset/1":
            return asset
        if path == "asset":
            return {"data": [asset]}
        if path == "app":
            assert kwargs["params"] == {
                "_filter_name": '"' + str(reference) + '"',
                "page_size": 2,
            }
            return {
                "data": (
                    []
                    if reference == "missing"
                    else [{"id": 5}, {"id": 6}]
                    if reference == "duplicate"
                    else [{"id": 5}]
                )
            }
        return {"configuration": {}}

    client.get.side_effect = get
    client.post.return_value = {"id": 2}
    args = (
        ["assets", "update", "1", "--description", "changed"]
        if command == "assets"
        else [
            "actions",
            "run",
            "--action",
            "lookup domain",
            "--asset",
            "fixture",
            "--container",
            "1",
        ]
    )
    with (
        patch(PATCH_RESOLVE, return_value=soar_cfg()),
        patch(PATCH_CLIENT, return_value=client),
        patch("splunkctl.guard.cfg_mod.resolve_soar", return_value=soar_cfg()),
    ):
        result = CliRunner().invoke(cli, ["--json", "--yes", "soar", *args])
    assert result.exit_code == (1 if reference in ("missing", "duplicate") else 0), (
        result.output
    )
    if reference in ("missing", "duplicate"):
        client.post.assert_not_called()
        assert ("not_found" if reference == "missing" else "ambiguous") in result.output
        assert (
            f"App '{reference}' not found."
            if reference == "missing"
            else f"Ambiguous: multiple apps named '{reference}'"
        ) in result.output
    else:
        body = client.post.call_args.kwargs["body"]
        if command == "assets":
            assert body["app_id"] == 5
            assert body["configuration"] == {"keep": "value"}
            client.get.assert_any_call("app/5", params={})
        else:
            assert body["targets"][0]["app_id"] == 5
