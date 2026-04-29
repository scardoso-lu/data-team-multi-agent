import json

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
            }
        ),
        encoding="utf-8",
    )

    config = AppConfig(config_path)

    assert config.agent_value("example", "column") == "Input"
    assert config.require("runtime", "poll_interval_seconds") == 1
