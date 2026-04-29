from approvals import REJECTED, TIMED_OUT
from harness.run import run_once
from events import (
    APPROVAL_RECEIVED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    APPROVAL_TIMED_OUT,
    ARTIFACT_CREATED,
    WORK_ITEM_CLAIMED,
    WORK_ITEM_MOVED,
)


def test_harness_runs_work_item_to_terminal_column():
    work_item_id = "workflow-1"
    harness = run_once(work_item_id=work_item_id)
    config = harness["config"]
    terminal_column = config.agent_value("data_steward", "next_column")

    assert [result["status"] for result in harness["results"]] == [
        "processed",
        "processed",
        "processed",
        "processed",
        "processed",
    ]
    assert harness["board"].columns[terminal_column] == [work_item_id]
    assert len(harness["teams"].approval_requests) == 4
    assert len(harness["teams"].notifications) == 1
    assert len(harness["governance"].metadata) == 2
    assert harness["board"].artifacts[work_item_id] == config.require(
        "governance",
        "audit_results",
    )

    event_types = [event["type"] for event in harness["events"].events]
    assert event_types.count(WORK_ITEM_CLAIMED) == 5
    assert event_types.count(ARTIFACT_CREATED) == 5
    assert event_types.count(WORK_ITEM_MOVED) == 5
    assert event_types.count(APPROVAL_REQUESTED) == 4
    assert event_types.count(APPROVAL_RECEIVED) == 4


def test_harness_routes_rejected_approval_to_rework():
    work_item_id = "workflow-reject-1"
    harness = run_once(
        work_item_id=work_item_id,
        approval_decision=REJECTED,
        approval_comments="Revise the architecture",
    )
    config = harness["config"]
    rework_column = config.require("runtime", "rework_column")

    assert harness["results"][0]["status"] == "skipped"
    assert harness["results"][0]["reason"] == "approval_rejected"
    assert harness["board"].columns[rework_column] == [work_item_id]

    event_types = [event["type"] for event in harness["events"].events]
    assert event_types.count(APPROVAL_REQUESTED) == 1
    assert event_types.count(APPROVAL_REJECTED) == 1
    rejected_event = [
        event for event in harness["events"].events if event["type"] == APPROVAL_REJECTED
    ][0]
    assert rejected_event["payload"]["decided_by"] == "harness-reviewer"
    assert rejected_event["payload"]["comments"] == "Revise the architecture"


def test_harness_routes_timed_out_approval_to_timeout_column():
    work_item_id = "workflow-timeout-1"
    harness = run_once(work_item_id=work_item_id, approval_decision=TIMED_OUT)
    config = harness["config"]
    timeout_column = config.require("runtime", "approval_timeout_column")

    assert harness["results"][0]["status"] == "skipped"
    assert harness["results"][0]["reason"] == "approval_timed_out"
    assert harness["board"].columns[timeout_column] == [work_item_id]

    event_types = [event["type"] for event in harness["events"].events]
    assert event_types.count(APPROVAL_REQUESTED) == 1
    assert event_types.count(APPROVAL_TIMED_OUT) == 1
