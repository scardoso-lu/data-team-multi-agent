import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHARED_SKILLS_DIR = os.path.join(ROOT_DIR, "shared_skills")
if SHARED_SKILLS_DIR not in sys.path:
    sys.path.insert(0, SHARED_SKILLS_DIR)

from agents.data_analyst.app import DataAnalystAgent
from agents.data_architect.app import DataArchitectAgent
from agents.data_engineer.app import DataEngineerAgent
from agents.data_steward.app import DataStewardAgent
from agents.qa_engineer.app import QAEngineerAgent
from config import AppConfig
from events import EventRecorder
from harness.fakes import (
    FakeApprovalClient,
    FakeBoardClient,
    FakeFabricClient,
    FakeGovernanceClient,
    FakeNotificationClient,
)


def build_harness(work_item_id="local-1"):
    config = AppConfig()
    first_column = config.agent_value("data_architect", "column")
    board = FakeBoardClient(
        columns={first_column: [work_item_id]},
        details={work_item_id: {"requirements": "local harness workflow"}},
    )
    teams = FakeNotificationClient()
    approvals = FakeApprovalClient(decision="approved")
    fabric = FakeFabricClient()
    governance = FakeGovernanceClient()
    events = EventRecorder()

    agents = [
        DataArchitectAgent(ado=board, teams=teams, approvals=approvals, config=config, events=events),
        DataEngineerAgent(ado=board, teams=teams, fabric=fabric, approvals=approvals, config=config, events=events),
        QAEngineerAgent(ado=board, teams=teams, fabric=fabric, approvals=approvals, config=config, events=events),
        DataAnalystAgent(ado=board, teams=teams, purview=governance, approvals=approvals, config=config, events=events),
        DataStewardAgent(ado=board, teams=teams, purview=governance, config=config, events=events),
    ]

    return {
        "config": config,
        "board": board,
        "teams": teams,
        "approvals": approvals,
        "fabric": fabric,
        "governance": governance,
        "events": events,
        "agents": agents,
        "work_item_id": work_item_id,
    }


def run_once(work_item_id="local-1"):
    harness = build_harness(work_item_id=work_item_id)
    results = [agent.process_next_item() for agent in harness["agents"]]
    harness["results"] = results
    return harness


def main():
    harness = run_once()
    terminal_column = harness["config"].agent_value("data_steward", "next_column")
    print(
        {
            "results": harness["results"],
            "terminal_items": harness["board"].columns.get(terminal_column, []),
        }
    )


if __name__ == "__main__":
    main()
