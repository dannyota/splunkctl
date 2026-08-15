"""Browser session record, store, and target config resolution.

Sessions live under ``~/.splunkctl/sessions/<profile>/<target>.json`` with
0700/0600 permissions and atomic writes. The store never logs or returns
session values in messages; callers render them, and the values map is kept
out of every error string.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from splunkctl import config as cfg_mod

type Target = Literal["siem", "soar"]


class SessionError(RuntimeError):
    """A session-store or target-config failure with an ``errors.py`` kind."""

    def __init__(self, message: str, *, kind: str = "error") -> None:
        """Store the message and ``errors.py`` kind for callers to report."""
        super().__init__(message)
        self.message = message
        self.kind = kind


@dataclass(frozen=True)
class SessionRecord:
    """One validated product session, ready to serialize to disk."""

    target: Target
    profile: str
    origin: str
    values: dict[str, str]
    acquired_at: float
    last_validated_at: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this record."""
        return {
            "target": self.target,
            "profile": self.profile,
            "origin": self.origin,
            "values": self.values,
            "acquired_at": self.acquired_at,
            "last_validated_at": self.last_validated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        """Rebuild a record from the output of :meth:`to_dict`."""
        return cls(
            target=data["target"],
            profile=data["profile"],
            origin=data["origin"],
            values=dict(data.get("values", {})),
            acquired_at=float(data.get("acquired_at", 0)),
            last_validated_at=float(data.get("last_validated_at", 0)),
        )


@dataclass(frozen=True)
class TargetAuth:
    """Resolved product endpoints for one browser-authenticated target."""

    target: Target
    profile: str
    web_url: str
    api_base: str
    verify: bool
    timeout: int


def _origin(scheme: str, host: str, port: int) -> str:
    return f"{scheme}://{host}:{port}"


def resolve_target(
    config_path: Path | None,
    profile: str | None,
    target: Target,
    *,
    timeout: int = 30,
) -> TargetAuth:
    """Resolve the browser origin and validation base for ``target``.

    SIEM uses ``web_url`` as the browser origin and the management API
    (``scheme://host:port``, normally 8089) as the validation base. SOAR uses
    one origin for both; ``web_url`` defaults to ``https://host:port`` when
    unset. The profile name is resolved from config so the session path is
    stable regardless of how the profile was selected.
    """
    if target == "siem":
        cfg = cfg_mod.load(config_path, profile=profile)
        name = cfg_mod.resolve(config_path, profile=profile)["profile"]
        web_url = cfg.get("web_url")
        if not web_url:
            raise SessionError(
                "SIEM browser authentication requires 'web_url' in the profile. "
                "Run 'splunkctl config init' to set it.",
                kind="usage",
            )
        scheme = cfg.get("scheme", "https")
        host = cfg.get("host", "localhost")
        port = int(cfg.get("port", 8089))
        return TargetAuth(
            target="siem",
            profile=name,
            web_url=str(web_url),
            api_base=_origin(scheme, host, port),
            verify=bool(cfg.get("verify", True)),
            timeout=timeout,
        )

    cfg = cfg_mod.resolve_soar(config_path, profile=profile)
    name = cfg_mod.resolve(config_path, profile=profile)["profile"]
    host = cfg.get("host")
    if not host:
        raise SessionError(
            "No SOAR host configured. Run 'splunkctl config init --soar'.",
            kind="usage",
        )
    port = int(cfg.get("port", 8443))
    web_url = str(cfg.get("web_url") or _origin("https", host, port))
    return TargetAuth(
        target="soar",
        profile=name,
        web_url=web_url,
        api_base=web_url,
        verify=bool(cfg.get("verify", True)),
        timeout=timeout,
    )


def sessions_dir() -> Path:
    """Return the session directory (derived from config so tests isolate it)."""
    return cfg_mod.DEFAULT_DIR / "sessions"


def session_path(profile: str, target: Target) -> Path:
    """Return the on-disk path for a profile's target session."""
    return sessions_dir() / profile / f"{target}.json"


def save(profile: str, record: SessionRecord) -> None:
    """Write ``record`` atomically with 0600 perms in a 0700 directory."""
    path = session_path(profile, record.target)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, stat.S_IRWXU)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)


def load(
    profile: str,
    target: Target,
    *,
    expected_origin: str,
) -> SessionRecord | None:
    """Read a session; ``None`` when missing, unparseable, or mis-bound.

    A record whose profile, target, or origin does not match the current
    configuration is treated as absent (and must be re-created by login).
    """
    path = session_path(profile, target)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        record = SessionRecord.from_dict(data)
    except (ValueError, KeyError, TypeError):
        return None
    if (
        record.target != target
        or record.profile != profile
        or record.origin != expected_origin
    ):
        return None
    return record


def delete(profile: str, target: Target) -> None:
    """Remove a session file. Raises :class:`SessionError` on failure."""
    path = session_path(profile, target)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise SessionError(
            f"Could not remove session file {path}", kind="error"
        ) from exc
