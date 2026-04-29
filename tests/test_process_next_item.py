from agents.data_architect.app import DataArchitectAgent
from config import AppConfig
from approvals import REJECTED
from events import AGENT_FAILED, APPROVAL_REJECTED, EventRecorder
from harness.fakes import FakeApprovalClient, FakeBoardClient, FakeNotificationClient


class FallbackLLM:
    def complete_json(self, task, payload, fallback=None):
        return fallback


def business_requirements(config):
    return {
        "work_item_type": "Feature",
        "title": "Customer order analytics",
        "requirements": "customer order analytics",
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }


def test_process_next_item_skips_when_no_work_items():
    config = AppConfig()
    board = FakeBoardClient(columns={})
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_work_items"


def test_process_next_item_does_not_move_on_approval_timeout():
    config = AppConfig()
    work_item_id = "timeout-1"
    start_column = config.agent_value("data_architect", "column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={work_item_id: business_requirements(config)},
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(approved=False),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "approval_timed_out"
    assert board.columns[config.require("runtime", "approval_timeout_column")] == [work_item_id]


def test_process_next_item_retries_transient_failures():
    config = AppConfig()
    work_item_id = "retry-1"
    start_column = config.agent_value("data_architect", "column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={work_item_id: business_requirements(config)},
        failures={"get_work_item_details": 1},
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "processed"
    assert board.failures["get_work_item_details"] == 0


def test_process_next_item_moves_permanent_failures_to_error_column():
    config = AppConfig()
    events = EventRecorder()
    work_item_id = "failure-1"
    start_column = config.agent_value("data_architect", "column")
    error_column = config.require("runtime", "error_column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        failures={"get_work_item_details": 10},
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
        events=events,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "failed"
    assert result["moved_to"] == error_column
    assert board.columns[error_column] == [work_item_id]
    assert events.events[-1]["type"] == AGENT_FAILED


def test_process_next_item_moves_rejections_to_rework_column():
    config = AppConfig()
    events = EventRecorder()
    work_item_id = "reject-1"
    start_column = config.agent_value("data_architect", "column")
    rework_column = config.require("runtime", "rework_column")
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={work_item_id: business_requirements(config)},
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(
            decision=REJECTED,
            decided_by="reviewer@example.com",
            comments="Revise the model",
        ),
        config=config,
        events=events,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "approval_rejected"
    assert result["moved_to"] == rework_column
    assert board.columns[rework_column] == [work_item_id]
    rejected_event = [event for event in events.events if event["type"] == APPROVAL_REJECTED][0]
    assert rejected_event["payload"]["decided_by"] == "reviewer@example.com"
    assert rejected_event["payload"]["comments"] == "Revise the model"


def test_data_architect_blocks_when_business_io_examples_are_missing():
    config = AppConfig()
    work_item_id = "missing-examples-1"
    start_column = config.agent_value("data_architect", "column")
    teams = FakeNotificationClient()
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={work_item_id: {"requirements": "missing examples"}},
    )
    agent = DataArchitectAgent(
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
    assert teams.notifications[0]["title"] == f"Work Item {work_item_id} Needs Business Examples"
    assert teams.notifications[0]["work_item_id"] == work_item_id


def test_data_architect_allows_human_confirmed_exploration_without_examples():
    config = AppConfig()
    work_item_id = "exploration-1"
    start_column = config.agent_value("data_architect", "column")
    next_column = config.agent_value("data_architect", "next_column")
    teams = FakeNotificationClient()
    board = FakeBoardClient(
        columns={start_column: [work_item_id]},
        details={
            work_item_id: {
                "fields": {
                    "System.WorkItemType": "Issue",
                    "System.Title": "Explore churn signals",
                    "System.Description": "Find likely signals for churn analysis.",
                    "System.Tags": "is_exploration_topic",
                }
            }
        },
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=teams,
        approvals=FakeApprovalClient(),
        config=config,
        llm=FallbackLLM(),
    )

    result = agent.process_next_item()

    assert result["status"] == "processed"
    assert board.columns[next_column] == [work_item_id]
    assert result["artifact"]["exploration_mode"] is True
    assert result["artifact"]["requires_human_spec_validation"] is True
    assert result["artifact"]["business_io_examples"][0]["generated_by_agent"] is True
    assert teams.notifications[0]["title"] == f"Work Item {work_item_id} Exploration Fallback Applied"
