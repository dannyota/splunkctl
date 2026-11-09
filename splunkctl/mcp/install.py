"""Project-scoped MCP registration adapters."""

import json
import os
import stat
import sys
import uuid
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


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _replace(dest: Path, text: str, directory_fd: int) -> None:
    try:
        mode = stat.S_IMODE(
            os.stat(dest.name, dir_fd=directory_fd, follow_symlinks=False).st_mode
        )
    except FileNotFoundError:
        mode = 0o600
    temporary = f".{dest.name}.{uuid.uuid4().hex}"
    fd = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode, dir_fd=directory_fd
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(
            temporary, dest.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
        )
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def install(directory: Path, **kwargs: Any) -> tuple[Path, bool, dict[str, object]]:
    """Hold the verified config directory open through reading and replacement."""
    dest = directory / _FILES[kwargs["client"]]
    directory_fd = None
    try:
        if dest.parent.is_symlink() or dest.is_symlink():
            raise ValueError("symlinked configuration directory or destination")
        if not kwargs["preview"]:
            dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.parent.exists():
            directory_fd = os.open(
                dest.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                info = os.stat(dest.name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError("symlinked configuration destination")
        return _install(directory, directory_fd=directory_fd, **kwargs)
    except (ValueError, OSError) as exc:
        output.error(f"Cannot edit {dest}: {exc}", kind="usage")
        raise SystemExit(2) from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _install(
    directory: Path,
    *,
    directory_fd: int | None,
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
    raw = ""
    exists = False
    if directory_fd is not None:
        try:
            fd = os.open(dest.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        else:
            exists = True
            with os.fdopen(fd, encoding="utf-8") as stream:
                raw = stream.read()
    try:
        config = (
            tomlkit.parse(raw)
            if client == "codex"
            else json.loads(
                raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object
            )
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
        if directory_fd is None:
            raise ValueError("Configuration directory is unavailable")
        _replace(dest, text, directory_fd)
    return dest, changed, entry
