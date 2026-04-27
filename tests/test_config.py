import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from config import AppConfig


def test_config_loads_agent_values_from_file():
    config = AppConfig()

    architect = config.agent("data_architect")

    assert architect["column"] == "Architecture"
    assert architect["next_column"] == "Engineering"
    assert architect["port"] == 5000


def test_config_supports_explicit_config_path(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {"example": {"column": "Input"}},
                "runtime": {"poll_interval_seconds": 1},
                "secrets": {"token_env": "EXAMPLE_TOKEN"},
            }
        ),
        encoding="utf-8",
    )

    config = AppConfig(config_path)

    assert config.agent_value("example", "column") == "Input"
    assert config.require("runtime", "poll_interval_seconds") == 1


def test_config_reads_values_from_named_environment_variables(monkeypatch):
    config = AppConfig()
    monkeypatch.setenv("ADO_PAT", "token-value")

    assert config.from_env("ado", "pat_env") == "token-value"
