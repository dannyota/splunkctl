"""MCP server with progressive disclosure via 5 meta-tools."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from typing import Any

import click
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata
from mcp.types import ToolAnnotations
from pydantic import ConfigDict

from splunkctl import __version__
from splunkctl.mcp.output_cap import (
    MAX_OUTPUT_BYTES,
    SUBPROCESS_TIMEOUT,
    spill_output,
    sweep_spill_dir,
    timeout_message,
    truncate_utf8,
)
from splunkctl.mcp.resources import load_guides
from splunkctl.mcp.tools import (
    SKIP_PARAMS,
    ToolEntry,
    ToolIndex,
    build_tool_index,
    direct_commands,
    group_names,
    group_summary,
    group_tools,
    has_subgroups,
    leaf_count,
    subgroup_names,
)

_INSTRUCTIONS = """\
splunkctl is a CLI for Splunk Enterprise SIEM operations. Start with \
`help` to see command groups, then `focus <group>` to load typed tools — \
the preferred way to run commands (validated arguments, full schemas). \
`usage <command>` previews one command's schema and auto-loads it as a \
callable tool. `run` is an escape hatch for raw command strings (no \
validation). `unfocus` when done to free context. Mutations are guarded: \
pass yes=true to apply (dry-run by default). \
The soar tree has nested subgroups (containers, playbooks, actions, ...); \
focus at subgroup granularity: `focus "soar containers"`, not `focus soar`. \
`help soar` lists available subgroups."""

_FORCE_FLAGS = ["--json"]

_STRIP_PARAMS = SKIP_PARAMS


def _decode_stream(data: bytes) -> str:
    """Decode subprocess output, tolerating binary payloads.

    Commands like ``soar playbooks export`` emit raw bytes (a tgz) on
    stdout when ``--out`` is omitted — surface a hint instead of dying
    on a UTF-8 decode error.
    """
    try:
        return data.decode()
    except UnicodeDecodeError:
        return f"(binary output: {len(data)} bytes — pass --out FILE to save it)"


def _exec_cli(args: list[str]) -> str:
    """Run ``splunkctl <args>`` as a subprocess and return output."""
    cmd = [sys.executable, "-m", "splunkctl", *args, *_FORCE_FLAGS]
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return timeout_message()
    out = _decode_stream(result.stdout).strip()
    err = _decode_stream(result.stderr).strip()
    if result.returncode != 0:
        text = err or out or f"Command failed with exit code {result.returncode}"
        return truncate_utf8(text, MAX_OUTPUT_BYTES)
    if err and out:
        text = f"{err}\n\n{out}"
    else:
        text = out or err or "(no output)"
    if len(text.encode()) > MAX_OUTPUT_BYTES:
        return spill_output(text)
    return text


def _split_command(raw: str) -> list[str]:
    """Shell-style tokenizer that respects quotes."""
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def _coerce_array(entry: ToolEntry, pname: str, value: Any) -> Any:
    """Parse a JSON-encoded array string for array-typed params.

    Some MCP clients serialize list arguments as JSON strings; the
    pass-through arg model does no pre-parsing, so unwrap here.
    """
    prop = entry.schema.get("properties", {}).get(pname, {})
    if prop.get("type") == "array" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, list):
            return parsed
    return value


def _build_cli_args(entry: ToolEntry, params: dict[str, Any]) -> list[str]:
    """Convert typed tool parameters to CLI arg list."""
    args = list(entry.cmd_path)
    positional: dict[str, list[str]] = {}
    for pname, raw in params.items():
        if pname in _STRIP_PARAMS:
            if pname == "yes" and raw:
                args.append("--yes")
            continue
        value = _coerce_array(entry, pname, raw)
        if pname in entry.positional:
            items = value if isinstance(value, list) else [value]
            positional[pname] = [str(v) for v in items]
            continue
        # Renamed Click options (--severity → severity_override) make the
        # schema name diverge from the CLI flag; the entry's flag map is
        # authoritative.
        flag = entry.flags.get(pname, f"--{pname.replace('_', '-')}")
        if isinstance(value, bool):
            if value:
                args.append(flag)
            elif pname in entry.neg_flags:
                args.append(entry.neg_flags[pname])
        elif isinstance(value, list):
            for item in value:
                args.extend([flag, str(item)])
        else:
            args.extend([flag, str(value)])
    for pname in entry.arg_order:
        args.extend(positional.pop(pname, []))
    for leftovers in positional.values():
        args.extend(leftovers)
    return args


def create_server() -> FastMCP:
    """Build the MCP server with meta-tools and guide resources."""
    from splunkctl.main import cli

    mcp = FastMCP(
        name="splunkctl",
        instructions=_INSTRUCTIONS,
    )
    mcp._mcp_server.version = __version__

    from mcp.server.lowlevel.server import NotificationOptions

    _orig = mcp._mcp_server.create_initialization_options

    def _init_opts_with_list_changed(**kwargs: Any) -> Any:
        kwargs.setdefault(
            "notification_options",
            NotificationOptions(tools_changed=True),
        )
        return _orig(**kwargs)

    mcp._mcp_server.create_initialization_options = _init_opts_with_list_changed  # type: ignore[assignment]

    all_tools: ToolIndex = build_tool_index(cli)
    focused: dict[str, list[str]] = {}

    # --- Meta-tool: help ---

    @mcp.tool(
        name="help",
        description="List command groups, or subcommands within a group.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def help_tool(group: str | None = None) -> str:
        """List command groups, or subcommands within a group."""
        if group is None:
            rows = group_summary(cli)
            lines: list[str] = []
            for r in rows:
                line = f"{r['group']:16s} {r['description']} ({r['count']} cmds)"
                lines.append(line)
                if "subgroups" in r:
                    lines.append(f"{'':16s}   subgroups: {r['subgroups']}")
                    lines.append(
                        f"{'':16s}   focus at subgroup level: "
                        f'focus "{r["group"]} <subgroup>"'
                    )
            return "\n".join(lines)
        # For groups with subgroups, show the two-level layout
        parts = _split_command(group)
        if len(parts) == 1 and has_subgroups(cli, parts[0]):
            grp = parts[0]
            top_cmd = cli.commands.get(grp)
            if not isinstance(top_cmd, click.Group):  # guaranteed by has_subgroups
                raise TypeError(f"expected group for {grp!r}")
            sg = subgroup_names(cli, grp)
            dc = direct_commands(cli, grp)
            lines = [f'{grp} subgroups (focus "{grp} <subgroup>"):']
            for s in sg:
                sub_cmd = top_cmd.commands[s]
                desc = (sub_cmd.help or "").split("\n")[0]
                n = leaf_count(sub_cmd) if isinstance(sub_cmd, click.Group) else 0
                lines.append(f"  {grp} {s:16s} {desc} ({n} cmds)")
            if dc:
                lines.append(f"\n{grp} direct commands:")
                for c in dc:
                    sub_cmd = top_cmd.commands[c]
                    desc = (sub_cmd.help or "").split("\n")[0]
                    lines.append(f"  {grp} {c:16s} {desc}")
            return "\n".join(lines)
        return _exec_cli([*parts, "--help"])

    # --- Meta-tool: usage ---

    @mcp.tool(
        name="usage",
        description=(
            "Show flags, args, and description for one command. "
            "Auto-loads it as a callable tool. "
            'Accepts nested paths: usage "soar playbooks run".'
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def usage_tool(command: str, ctx: Context) -> str:  # type: ignore[type-arg]
        """Show full schema for one command and auto-load it."""
        tool_name = command.strip().replace(" ", "_").replace("-", "_")
        entry = all_tools.get(tool_name)
        if entry is None:
            return f"Unknown command: {command}"

        if not any(tool_name in names for names in focused.values()):
            _register_tool(mcp, entry)
            focused.setdefault("_usage", []).append(tool_name)
            await ctx.session.send_tool_list_changed()

        return json.dumps(
            {
                "name": entry.name,
                "description": entry.description,
                "guarded": entry.guarded,
                "inputSchema": entry.schema,
            },
            indent=2,
        )

    # --- Meta-tool: focus ---

    @mcp.tool(
        name="focus",
        description=(
            "Load typed tools for a command group (enables full schemas). "
            "Preferred over run for validated arguments. "
            'Nested groups like soar require subgroup: focus "soar containers".'
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def focus_tool(group: str, ctx: Context) -> str:  # type: ignore[type-arg]
        """Load typed tools for a command group."""
        if group in focused:
            count = len(focused[group])
            return f"Group '{group}' already focused ({count} tools)."

        # Reject bare groups that have nested subgroups (too many tools).
        parts = _split_command(group)
        if len(parts) == 1 and has_subgroups(cli, parts[0]):
            sg = subgroup_names(cli, parts[0])
            dc = direct_commands(cli, parts[0])
            lines = [
                f"'{parts[0]}' has nested subgroups — focus at "
                f"subgroup level to avoid flooding context.",
                "",
                "Subgroups:",
            ]
            for s in sg:
                lines.append(f'  focus "{parts[0]} {s}"')
            if dc:
                lines.append(
                    f"\nDirect commands ({', '.join(dc)}) can be "
                    f"loaded individually via usage."
                )
            return "\n".join(lines)

        entries = group_tools(all_tools, group)
        if not entries:
            available = group_names(cli)
            return (
                f"No tools found for group '{group}'. Available: {', '.join(available)}"
            )

        names: list[str] = []
        for entry in entries:
            _register_tool(mcp, entry)
            names.append(entry.name)
        focused[group] = names
        await ctx.session.send_tool_list_changed()

        lines = [f"Loaded {len(names)} tools for '{group}':"]
        for entry in entries:
            tag = " [guarded]" if entry.guarded else ""
            lines.append(f"  {entry.name}{tag} — {entry.description}")
        return "\n".join(lines)

    # --- Meta-tool: unfocus ---

    @mcp.tool(
        name="unfocus",
        description="Unload a command group's typed tools to free context.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def unfocus_tool(
        group: str | None = None,
        ctx: Context = None,  # type: ignore[type-arg,assignment]
    ) -> str:
        """Unload a command group or all groups."""
        if group is None:
            removed = 0
            for names in focused.values():
                for n in names:
                    try:
                        mcp.remove_tool(n)
                    except Exception:  # noqa: BLE001, S110
                        pass
                    removed += 1
            focused.clear()
            if ctx is not None:
                await ctx.session.send_tool_list_changed()
            return f"Unloaded all focused tools ({removed} total)."

        # Try exact key first, then normalized form for subgroup paths
        key = group if group in focused else None
        if key is None:
            norm = group.replace(" ", "_").replace("-", "_")
            for k in focused:
                if k.replace(" ", "_").replace("-", "_") == norm:
                    key = k
                    break
        if key is None:
            return f"Group '{group}' is not focused."
        for n in focused[key]:
            try:
                mcp.remove_tool(n)
            except Exception:  # noqa: BLE001, S110
                pass
        count = len(focused.pop(key))
        if ctx is not None:
            await ctx.session.send_tool_list_changed()
        return f"Unloaded {count} tools for '{group}'."

    # --- Meta-tool: run ---

    @mcp.tool(
        name="run",
        description=(
            "Run any splunkctl command. Pass the full command "
            "(e.g. 'search run index=main | head 10'). "
            "Use shell-style quoting for values with spaces. "
            "Prefer focus + typed tools for complex commands."
        ),
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def run_tool(command: str, yes: bool = False) -> str:
        """Execute a raw splunkctl command string."""
        tokens = _split_command(command)
        # The tool's yes parameter is the only mutation switch — a --yes
        # smuggled inside the command string must not bypass the guard.
        # Reject rather than silently strip: after shlex a quoted option
        # VALUE of '-y' is indistinguishable from the flag, and eating
        # it would shift arguments or corrupt the value.
        if any(t in ("--yes", "-y") for t in tokens):
            return (
                "Error: '--yes'/'-y' is not accepted inside the command "
                "string — the tool's yes parameter is the only mutation "
                "switch. Remove it and pass yes=true to apply. If you "
                "need the literal value '-y', use a focused typed tool "
                "instead."
            )
        if yes:
            tokens.append("--yes")
        result = _exec_cli(tokens)

        tool_name = "_".join(
            t.replace("-", "_") for t in tokens if not t.startswith("-")
        )
        if tool_name in all_tools and not any(
            tool_name in names for names in focused.values()
        ):
            if len(tokens) >= 2 and tokens[1] in subgroup_names(cli, tokens[0]):
                suggestion = f'focus "{tokens[0]} {tokens[1]}"'
            elif has_subgroups(cli, tokens[0]):
                # Bare focus on a nested group is refused; point at usage
                # for direct commands instead.
                suggestion = f'usage "{" ".join(tokens[:2])}"'
            else:
                suggestion = f"focus {tokens[0]}"
            result += (
                f"\n\nTip: run `{suggestion}` to load a typed tool "
                f"with a validated schema for this command."
            )
        return result

    # --- Prompts ---

    from splunkctl.mcp.prompts import register_prompts

    register_prompts(mcp)

    # --- Guide resources ---

    for guide in load_guides():
        slug = guide["slug"]
        title = guide["title"]
        text = guide["text"]

        def _make_guide(content: str) -> Any:
            def _reader() -> str:
                return content

            return _reader

        mcp.resource(
            f"guide://{slug}",
            name=title,
            description=f"Guide: {title}",
            mime_type="text/markdown",
        )(_make_guide(text))

    return mcp


class _PassThroughArgs(ArgModelBase):
    """Arg model that forwards arbitrary fields to the CLI unvalidated.

    Focused tools advertise a Click-derived JSON Schema, but runtime
    validation belongs to Click itself — the subprocess rejects bad args
    with a usage error. FastMCP's default ``func_metadata`` would instead
    validate against the runner's ``**kwargs`` signature, which no client
    payload can ever satisfy.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    def model_dump_one_level(self) -> dict[str, Any]:
        """Return the extra (client-sent) fields as-is."""
        return dict(self.__pydantic_extra__ or {})


def _register_tool(mcp: FastMCP, entry: ToolEntry) -> None:
    """Register a focused tool that executes via subprocess.

    Constructs a Tool object directly to use the Click-derived JSON
    Schema instead of FastMCP's auto-generation from function signatures.
    """
    from mcp.server.fastmcp.tools import Tool as MCPTool

    annotations = ToolAnnotations(
        readOnlyHint=not entry.guarded,
        destructiveHint=entry.guarded,
    )

    async def _runner(**kwargs: Any) -> str:
        cli_args = _build_cli_args(entry, kwargs)
        return _exec_cli(cli_args)

    tool = MCPTool(
        fn=_runner,
        name=entry.name,
        title=None,
        description=entry.description,
        parameters=entry.schema,
        fn_metadata=FuncMetadata(arg_model=_PassThroughArgs),
        is_async=True,
        context_kwarg=None,
        annotations=annotations,
    )
    mcp._tool_manager._tools[tool.name] = tool


def run_server() -> None:
    """Create and run the MCP server on stdio."""
    sweep_spill_dir()
    server = create_server()
    server.run(transport="stdio")
