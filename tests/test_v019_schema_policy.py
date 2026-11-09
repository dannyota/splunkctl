"""New server and ACL leaves retain MCP and transport mutation policy."""

from unittest.mock import Mock

import pytest

from splunkctl.main import cli
from splunkctl.mcp.tools import build_tool_index
from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError
from splunkctl.transport import sdk_handler


def test_server_and_acl_mcp_schemas():
    tools = build_tool_index(cli)
    for name in (
        "server_introspection_queues",
        "server_introspection_indexer",
        "server_introspection_disk",
        "server_log_level_get",
        "acl_get",
    ):
        assert name in tools
        assert not tools[name].guarded
        assert "yes" not in tools[name].schema["properties"]
    logger = tools["server_log_level_set"]
    assert logger.guarded
    assert logger.schema["properties"]["yes"]["default"] is False
    assert logger.schema["properties"]["level"]["enum"] == [
        "DEBUG",
        "INFO",
        "WARN",
        "ERROR",
    ]
    assert set(logger.schema["required"]) == {"component", "level"}
    acl = tools["acl_set"]
    assert acl.guarded
    assert acl.schema["properties"]["yes"]["default"] is False
    assert acl.schema["properties"]["sharing"]["enum"] == ["user", "app", "global"]
    assert not any("pipelines" in name for name in tools)
    assert "mcp_install" not in tools


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/services/server/logger/TcpOutputProc", "level=DEBUG"),
        (
            "/servicesNS/admin/search/saved/searches/sc_live_acl_search/acl",
            "sharing=app&owner=admin",
        ),
    ],
)
def test_read_only_rejects_new_posts_at_sdk_dispatch(path, body):
    underlying = Mock()
    handler = sdk_handler(underlying, "https://example.test")
    with invocation("new mutation", True), pytest.raises(ReadOnlyError):
        handler(
            f"https://example.test{path}",
            {"method": "POST", "headers": [], "body": body},
        )
    underlying.assert_not_called()
