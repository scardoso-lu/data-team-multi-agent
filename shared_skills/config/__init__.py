# Runtime configuration loader.

import copy
import json
import os
from pathlib import Path


def _default_config_path():
    candidates = [
        os.getenv("CONFIG_PATH"),
        Path(__file__).resolve().parents[2] / "config" / "default.json",
        Path.cwd() / "config" / "default.json",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path

    raise FileNotFoundError("No config file found. Set CONFIG_PATH or add config/default.json.")


def load_config(path=None):
    """Load application config from JSON."""
    config_path = Path(path) if path else _default_config_path()
    with config_path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


class AppConfig:
    """Convenience wrapper for nested runtime configuration."""

    def __init__(self, path=None):
        self.data = load_config(path)

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def require(self, *keys):
        value = self.get(*keys)
        if value is None:
            joined = ".".join(keys)
            raise KeyError(f"Missing required config value: {joined}")
        return value

    def agent(self, agent_name):
        return self.require("agents", agent_name)

    def agent_value(self, agent_name, key, default=None):
        return self.agent(agent_name).get(key, default)

    def copy_value(self, *keys, default=None):
        return copy.deepcopy(self.get(*keys, default=default))
