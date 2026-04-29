from pathlib import Path

from agent_base import configure_agent_logger


def test_configure_agent_logger_creates_agent_log_folder(tmp_path):
    log_file = tmp_path / "logs" / "data_architect" / "data_architect.log"
    logger = configure_agent_logger(
        "tests.test_agent_logging.data_architect",
        log_file,
    )

    logger.info("log folder smoke test")

    assert log_file.exists()
    assert Path(log_file).parent.name == "data_architect"
