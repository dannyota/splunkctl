"""CLI subprocess execution and tool registration for the MCP server."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from splunkctl.mcp.output_cap import (
    MAX_OUTPUT_BYTES,
    SUBPROCESS_TIMEOUT,
    spill_output,
    timeout_message,
    truncate_utf8,
)
from splunkctl.mcp.tools import SKIP_PARAMS, ToolEntry

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


def exec_cli(args: list[str]) -> str:
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


def split_command(raw: str) -> list[str]:
    """Shell-style tokenizer that respects quotes."""
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def _coerce_array(entry: ToolEntry, pname: str, value: Any) -> Any:
    """Parse a JSON-encoded array string for array-typed params."""
    prop = entry.schema.get("properties", {}).get(pname, {})
    if prop.get("type") == "array" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, list):
            return parsed
    return value


def build_cli_args(entry: ToolEntry, params: dict[str, Any]) -> list[str]:
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


type ExecFn = Callable[[list[str]], str]
