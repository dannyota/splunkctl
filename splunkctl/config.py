"""Config file management — load, save, redact."""

import os
import stat
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DIR: Path = Path.home() / ".splunkctl"
DEFAULT_PATH: Path = DEFAULT_DIR / "config.yaml"

_SECRETS: frozenset[str] = frozenset({"password", "token", "secret"})

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


def load(path: Path | None = None) -> dict[str, Any]:
    """Load config with resolution: defaults -> file -> env vars."""
    cfg = defaults()
    config_path = path or DEFAULT_PATH

    if config_path.exists():
        with open(config_path) as f:
            file_cfg = yaml.safe_load(f)
        if isinstance(file_cfg, dict):
            cfg.update(file_cfg)

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

    return cfg


def save(cfg: dict[str, Any], path: Path | None = None) -> Path:
    """Save config to YAML with 0600 permissions."""
    config_path = path or DEFAULT_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(dict(cfg), f, default_flow_style=False, sort_keys=False)

    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return config_path


def redact(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secret values replaced by '****'."""
    return {k: "****" if k in _SECRETS and v else v for k, v in cfg.items()}
