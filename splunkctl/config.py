"""Config file management — profiles (schema v2), legacy load, redact."""

import os
import stat
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml

DEFAULT_DIR: Path = Path.home() / ".splunkctl"
DEFAULT_PATH: Path = DEFAULT_DIR / "config.yaml"

PROFILES_KEY = "profiles"
CURRENT_KEY = "current"
_DEFAULT_PROFILE = "default"

_SECRETS: frozenset[str] = frozenset({"password", "token", "secret"})

# Fields that identify *which instance, as whom* — these decide the
# provenance ("source") reported for the guard banner. Non-identity
# fields (app, owner, verify, ...) can be overridden without changing
# who's-driving-the-mutation attribution.
_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {"host", "port", "scheme", "username", "password", "token"}
)

_ENV_MAP: dict[str, str] = {
    "SPLUNK_HOST": "host",
    "SPLUNK_PORT": "port",
    "SPLUNK_USER": "username",
    "SPLUNK_PASS": "password",
    "SPLUNK_SCHEME": "scheme",
    "SPLUNK_TOKEN": "token",
    "SPLUNK_APP": "app",
    "SPLUNK_OWNER": "owner",
    "SPLUNK_VERIFY": "verify",
}

type ConfigSource = Literal["profile", "env", "flags"]


class Resolved(TypedDict):
    """Effective config plus provenance, for the guard banner."""

    cfg: dict[str, Any]
    profile: str
    source: ConfigSource


class ProfileNotFoundError(Exception):
    """Raised when a named profile does not exist in the config file."""

    def __init__(self, name: str) -> None:
        """Store the missing profile name for callers to report."""
        self.name = name
        super().__init__(f"Profile '{name}' not found")


def defaults() -> dict[str, Any]:
    """Return default configuration values."""
    return {
        "host": "localhost",
        "port": 8089,
        "username": "admin",
        "password": "",
        "scheme": "https",
        "verify": False,
    }


def _read_raw(path: Path) -> dict[str, Any]:
    """Read a config file as a plain dict; {} if missing or empty."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _is_v2(raw: dict[str, Any]) -> bool:
    """True when the file uses the ``profiles:``/``current:`` schema."""
    return isinstance(raw.get(PROFILES_KEY), dict)


def _active_profile_name(raw: dict[str, Any], profile: str | None) -> str:
    """Resolve selection precedence: --profile flag > current: > default."""
    if profile:
        return profile
    if _is_v2(raw):
        current = raw.get(CURRENT_KEY)
        if isinstance(current, str) and current:
            return current
    return _DEFAULT_PROFILE


def _profile_config(raw: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one profile's fields, or raise if ``name`` is unknown.

    A v2 file requires an explicit ``profiles.<name>`` entry. A legacy
    (flat) or missing file only ever has the implicit ``default`` profile.
    """
    if _is_v2(raw):
        profiles = raw.get(PROFILES_KEY) or {}
        prof = profiles.get(name)
        if not isinstance(prof, dict):
            raise ProfileNotFoundError(name)
        return prof
    if name != _DEFAULT_PROFILE:
        raise ProfileNotFoundError(name)
    return raw


def profile_names(path: Path | None = None) -> list[str]:
    """List known profile names — ``["default"]`` for a legacy/missing file."""
    raw = _read_raw(path or DEFAULT_PATH)
    if _is_v2(raw):
        return sorted(raw.get(PROFILES_KEY) or {})
    return [_DEFAULT_PROFILE]


def _apply_env_overlay(cfg: dict[str, Any]) -> bool:
    """Overlay ``SPLUNK_*`` env vars onto ``cfg``; True if identity touched."""
    touched = False
    for env_key, cfg_key in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        if cfg_key == "port":
            try:
                cfg[cfg_key] = int(val)
            except ValueError:
                continue
        elif cfg_key == "verify":
            cfg[cfg_key] = val.lower() in ("1", "true", "yes")
        else:
            cfg[cfg_key] = val
        if cfg_key in _IDENTITY_FIELDS:
            touched = True
    return touched


def _apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any] | None) -> bool:
    """Overlay explicit CLI-flag overrides; True if identity touched."""
    if not overrides:
        return False
    touched = False
    for key, val in overrides.items():
        if val is None:
            continue
        cfg[key] = val
        if key in _IDENTITY_FIELDS:
            touched = True
    return touched


def resolve(
    path: Path | None = None,
    *,
    profile: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Resolved:
    """Resolve effective config with profile selection and provenance.

    Precedence is unchanged from the flat-config contract: ``overrides``
    (CLI flags) > env vars > profile (config file) > built-in defaults.
    ``source`` reports the highest-precedence layer that supplied a
    connection/credential field (host, port, scheme, username, password,
    token) — used to build the guard banner. Reads only the local config
    file and environment; never touches the network.

    Raises:
        ProfileNotFoundError: the selected profile does not exist.
    """
    cfg = defaults()
    config_path = path or DEFAULT_PATH
    raw = _read_raw(config_path)
    name = _active_profile_name(raw, profile)
    cfg.update(_profile_config(raw, name))

    source: ConfigSource = "profile"
    if _apply_env_overlay(cfg):
        source = "env"
    if _apply_overrides(cfg, overrides):
        source = "flags"

    return {"cfg": cfg, "profile": name, "source": source}


def load(path: Path | None = None, *, profile: str | None = None) -> dict[str, Any]:
    """Load config with resolution: defaults -> profile -> env vars."""
    return resolve(path, profile=profile)["cfg"]


def save(cfg: dict[str, Any], path: Path | None = None) -> Path:
    """Save config to YAML with 0600 permissions."""
    config_path = path or DEFAULT_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(dict(cfg), f, default_flow_style=False, sort_keys=False)

    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return config_path


def save_profile(cfg: dict[str, Any], name: str, path: Path | None = None) -> Path:
    """Create or update one named profile.

    A legacy flat file's existing keys are folded into ``profiles.default``
    first, upgrading the file to schema v2. An already-v2 file keeps its
    other profiles and ``current`` pointer untouched. Preserves 0600 perms.
    """
    config_path = path or DEFAULT_PATH
    raw = _read_raw(config_path)

    if _is_v2(raw):
        profiles = dict(raw.get(PROFILES_KEY) or {})
    elif raw:
        profiles = {_DEFAULT_PROFILE: raw}
    else:
        profiles = {}
    profiles[name] = cfg

    new_raw: dict[str, Any] = {PROFILES_KEY: profiles}
    if _is_v2(raw) and CURRENT_KEY in raw:
        new_raw[CURRENT_KEY] = raw[CURRENT_KEY]
    return save(new_raw, config_path)


def use_profile(name: str, path: Path | None = None) -> Path:
    """Point ``current`` at an existing profile. Never tests connectivity.

    Raises:
        ProfileNotFoundError: ``name`` is not a known profile.
    """
    config_path = path or DEFAULT_PATH
    raw = _read_raw(config_path)
    if name not in profile_names(config_path):
        raise ProfileNotFoundError(name)
    if _active_profile_name(raw, None) == name:
        return config_path

    if _is_v2(raw):
        new_raw = dict(raw)
    else:
        new_raw = {PROFILES_KEY: {_DEFAULT_PROFILE: raw}}
    new_raw[CURRENT_KEY] = name
    return save(new_raw, config_path)


def redact(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secret values replaced by '****'."""
    return {k: "****" if k in _SECRETS and v else v for k, v in cfg.items()}
