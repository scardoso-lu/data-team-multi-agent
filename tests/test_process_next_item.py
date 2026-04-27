import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from agents.data_architect.app import DataArchitectAgent
from config import AppConfig
from approvals import REJECTED
from events import AGENT_FAILED, APPROVAL_REJECTED, EventRecorder
from harness.fakes import FakeApprovalClient, FakeBoardClient, FakeNotificationClient


def test_process_next_item_skips_when_no_work_items():
    config = AppConfig()
    board = FakeBoardClient(columns={})
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_work_items"


def test_process_next_item_does_not_move_on_approval_timeout():
    config = AppConfig()
    work_item_id = "timeout-1"
    start_column = config.agent_value("data_architect", "column")
    board = FakeBoardClient(columns={start_column: [work_item_id]})
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(approved=False),
        config=config,
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
        failures={"get_work_item_details": 1},
    )
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        config=config,
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
    board = FakeBoardClient(columns={start_column: [work_item_id]})
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
    )

    result = agent.process_next_item()

    assert result["status"] == "skipped"
    assert result["reason"] == "approval_rejected"
    assert result["moved_to"] == rework_column
    assert board.columns[rework_column] == [work_item_id]
    rejected_event = [event for event in events.events if event["type"] == APPROVAL_REJECTED][0]
    assert rejected_event["payload"]["decided_by"] == "reviewer@example.com"
    assert rejected_event["payload"]["comments"] == "Revise the model"
