"""Project-scoped MCP registration adapters."""

import json
import os
import stat
import sys
import tempfile
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import tomlkit

from splunkctl import output
from splunkctl.mcp.transport import local_mcp_url

_FILES = {
    "claude": ".mcp.json",
    "codex": ".codex/config.toml",
    "cursor": ".cursor/mcp.json",
    "gemini": ".gemini/settings.json",
}
_MANAGED = frozenset({"command", "args", "url", "httpUrl", "type"})


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _invalid(dest: Path, entry: dict[str, object], reason: str) -> None:
    output.error(
        f"Cannot edit {dest}: {reason}. Add this splunkctl entry by hand:\n"
        + (
            tomlkit.dumps({"mcp_servers": {"splunkctl": entry}})
            if dest.suffix == ".toml"
            else json.dumps({"mcpServers": {"splunkctl": entry}}, indent=2)
        ),
        kind="usage",
    )
    raise SystemExit(2)


def _mapping(
    parent: MutableMapping[str, Any], key: str, dest: Path, entry: dict[str, object]
) -> MutableMapping[str, Any]:
    if key not in parent:
        parent[key] = {}
    value = parent[key]
    if not isinstance(value, MutableMapping):
        _invalid(dest, entry, f"{key} must be an object/table")
    return value  # type: ignore[no-any-return]


def _replace(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(dest.stat().st_mode) if dest.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{dest.name}.", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, dest)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(
    directory: Path,
    *,
    client: str,
    transport: str,
    host: str,
    port: int,
    preview: bool,
    read_only: bool,
) -> tuple[Path, bool, dict[str, object]]:
    """Merge managed fields, preserving settings and unchanged file bytes."""
    dest = directory / _FILES[client]
    if read_only and transport == "http":
        output.error(
            "--read-only requires stdio; "
            "URL registration cannot enforce server policy.",
            kind="usage",
        )
        raise SystemExit(2)
    entry: dict[str, object]
    if transport == "http":
        entry = {"httpUrl" if client == "gemini" else "url": local_mcp_url(host, port)}
        if client == "claude":
            entry["type"] = "http"
    else:
        args = ["-m", "splunkctl", "mcp", "serve"]
        if read_only:
            args.append("--read-only")
        entry = {"command": sys.executable, "args": args}
    exists = dest.exists()
    raw = dest.read_text(encoding="utf-8") if exists else ""
    try:
        config = (
            tomlkit.parse(raw)
            if client == "codex"
            else json.loads(raw, parse_constant=_reject_constant)
            if exists
            else {}
        )
    except (ValueError, tomlkit.exceptions.ParseError) as exc:
        _invalid(
            dest,
            entry,
            f"invalid {'TOML' if client == 'codex' else 'strict JSON'} ({exc})",
        )
    if not isinstance(config, MutableMapping):
        _invalid(dest, entry, "configuration must be an object/table")
    servers = _mapping(
        config, "mcp_servers" if client == "codex" else "mcpServers", dest, entry
    )
    server = _mapping(servers, "splunkctl", dest, entry)
    changed = any(server.get(key) != value for key, value in entry.items()) or any(
        key in server for key in _MANAGED - entry.keys()
    )
    for key in _MANAGED - entry.keys():
        server.pop(key, None)
    for key, value in entry.items():
        server[key] = value
    if changed and not preview:
        text = (
            tomlkit.dumps(config)
            if client == "codex"
            else json.dumps(config, indent=2) + "\n"
        )
        _replace(dest, text)
    return dest, changed, entry
