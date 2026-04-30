from agents.requirements_analyst.app import RequirementsAnalystAgent
from config import AppConfig
from harness.fakes import FakeApprovalClient, FakeBoardClient, FakeNotificationClient


class FallbackLLM:
    def complete_json(self, task, payload, fallback=None):
        return fallback


def _examples(config):
    return config.require("architecture", "business_io_examples")


def test_requirements_analyst_processes_work_item_with_examples():
    config = AppConfig()
    work_item_id = "ra-1"
    start_column = config.agent_value("requirements_analyst", "column")
    next_column = config.agent_value("requirements_analyst", "next_column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={
            work_item_id: {
                "work_item_type": "User Story",
                "title": "Build customer LTV",
                "business_io_examples": _examples(config),
            }
        },
    )

    agent = RequirementsAnalystAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "processed"
    assert board.columns[next_column] == [work_item_id]
    artifact = result["artifact"]
    assert artifact["work_item_type"] == "User Story"
    assert artifact["is_parent"] is False
    assert artifact["is_exploration"] is False
    assert len(artifact["business_io_examples"]) == 3
    assert "original_work_item" in artifact


def test_requirements_analyst_classifies_feature_as_parent():
    config = AppConfig()
    work_item_id = "ra-2"
    start_column = config.agent_value("requirements_analyst", "column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={
            work_item_id: {
                "work_item_type": "Feature",
                "title": "Analytics platform",
                "business_io_examples": _examples(config),
            }
        },
    )

    agent = RequirementsAnalystAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "processed"
    assert result["artifact"]["is_parent"] is True
    assert result["artifact"]["work_item_type"] == "Feature"


def test_requirements_analyst_blocks_when_examples_missing():
    config = AppConfig()
    work_item_id = "ra-3"
    start_column = config.agent_value("requirements_analyst", "column")
    teams = FakeNotificationClient()
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={work_item_id: {"title": "No examples here"}},
    )

    agent = RequirementsAnalystAgent(
        ado=board,
        teams=teams,
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_business_io_examples"
    assert board.columns[start_column] == [work_item_id]
    assert len(teams.notifications) == 1
    assert "Needs Business Examples" in teams.notifications[0]["title"]


def test_requirements_analyst_allows_exploration_without_examples():
    config = AppConfig()
    work_item_id = "ra-4"
    start_column = config.agent_value("requirements_analyst", "column")
    next_column = config.agent_value("requirements_analyst", "next_column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={
            work_item_id: {
                "fields": {
                    "System.WorkItemType": "Issue",
                    "System.Title": "Explore churn signals",
                    "System.Tags": "is_exploration_topic",
                }
            }
        },
    )

    agent = RequirementsAnalystAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "processed"
    assert board.columns[next_column] == [work_item_id]
    assert result["artifact"]["is_exploration"] is True
    assert result["artifact"]["business_io_examples"] == []
