"""MCP server extension for dynamically focused CLI tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.streamable_http import EventStore
from mcp.server.streamable_http_manager import DEFAULT_MAX_REQUEST_BODY_SIZE
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolResult,
    InputRequiredResult,
    TextContent,
    Tool,
    ToolAnnotations,
)

from splunkctl.mcp.runner import ExecFn, build_cli_args, exec_cli
from splunkctl.mcp.tools import ToolEntry
from splunkctl.mcp.transport import require_loopback_host


@dataclass(frozen=True)
class _RegisteredCLITool:
    """A Click-derived tool and its execution boundary."""

    entry: ToolEntry
    execute: ExecFn

    def describe(self) -> Tool:
        """Return the MCP protocol description for this tool."""
        return Tool(
            name=self.entry.name,
            description=self.entry.description,
            input_schema=self.entry.schema,
            annotations=ToolAnnotations(
                read_only_hint=not self.entry.guarded,
                destructive_hint=self.entry.guarded,
            ),
        )

    async def call(self, arguments: dict[str, Any]) -> CallToolResult:
        """Run the CLI tool and wrap its text as an MCP result."""
        cli_args = build_cli_args(self.entry, arguments)
        text = await anyio.to_thread.run_sync(self.execute, cli_args)
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            is_error=False,
        )


class SplunkMCPServer(MCPServer[None]):
    """MCPServer with an owned registry of focused splunkctl tools."""

    def __init__(
        self,
        name: str,
        *,
        instructions: str | None = None,
        version: str = "",
    ) -> None:
        """Initialize the MCP server and its dynamic CLI-tool registry."""
        super().__init__(name=name, instructions=instructions, version=version)
        self._cli_tools: dict[str, _RegisteredCLITool] = {}

    def add_cli_tool(
        self,
        entry: ToolEntry,
        execute: ExecFn | None = None,
    ) -> None:
        """Add or replace one Click-derived tool."""
        self._cli_tools[entry.name] = _RegisteredCLITool(
            entry=entry,
            execute=execute or exec_cli,
        )

    def remove_cli_tool(self, name: str) -> None:
        """Remove one Click-derived tool."""
        del self._cli_tools[name]

    def has_cli_tool(self, name: str) -> bool:
        """Return whether a Click-derived tool is currently registered."""
        return name in self._cli_tools

    async def list_tools(self) -> list[Tool]:
        """List decorator tools followed by the currently focused CLI tools."""
        tools = await super().list_tools()
        tools.extend(item.describe() for item in self._cli_tools.values())
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[None, Any] | None = None,
    ) -> CallToolResult | InputRequiredResult:
        """Dispatch a focused CLI tool or fall back to a decorator tool."""
        tool = self._cli_tools.get(name)
        if tool is not None:
            return await tool.call(arguments)
        return await super().call_tool(name, arguments, context)

    async def run_streamable_http_async(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        streamable_http_path: str = "/mcp",
        json_response: bool = False,
        stateless_http: bool = False,
        event_store: EventStore | None = None,
        retry_interval: int | None = None,
        max_request_body_size: int = DEFAULT_MAX_REQUEST_BODY_SIZE,
        transport_security: TransportSecuritySettings | None = None,
    ) -> None:
        """Run Streamable HTTP only on an allowed loopback host."""
        checked_host = require_loopback_host(host)
        await super().run_streamable_http_async(
            host=checked_host,
            port=port,
            streamable_http_path=streamable_http_path,
            json_response=json_response,
            stateless_http=stateless_http,
            event_store=event_store,
            retry_interval=retry_interval,
            max_request_body_size=max_request_body_size,
            transport_security=transport_security,
        )
