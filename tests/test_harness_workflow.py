import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.run import run_once
from events import (
    APPROVAL_RECEIVED,
    APPROVAL_REQUESTED,
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
    assert len(harness["fabric"].workspaces) == 1
    assert len(harness["fabric"].pipelines) == len(config.require("fabric", "pipelines"))
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
