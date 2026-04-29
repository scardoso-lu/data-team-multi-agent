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
    FakeGovernanceClient,
    FakeNotificationClient,
)


class HarnessLLMClient:
    """Keeps the harness deterministic while production agents use local CLIs."""

    def complete_json(self, task, payload, fallback=None):
        return fallback


def build_harness(work_item_id="local-1", approval_decision="approved", approval_comments=None):
    config = AppConfig()
    first_column = config.agent_value("data_architect", "column")
    board = FakeBoardClient(
        columns={first_column: [work_item_id]},
        details={
            work_item_id: {
                "work_item_type": "Feature",
                "title": "Local harness workflow",
                "requirements": "local harness workflow",
                "business_io_examples": config.require(
                    "architecture",
                    "business_io_examples",
                ),
            }
        },
    )
    teams = FakeNotificationClient()
    approvals = FakeApprovalClient(decision=approval_decision, comments=approval_comments)
    governance = FakeGovernanceClient()
    events = EventRecorder()
    llm = HarnessLLMClient()

    agents = [
        DataArchitectAgent(ado=board, teams=teams, approvals=approvals, config=config, events=events, llm=llm),
        DataEngineerAgent(ado=board, teams=teams, approvals=approvals, config=config, events=events, llm=llm),
        QAEngineerAgent(ado=board, teams=teams, approvals=approvals, config=config, events=events, llm=llm),
        DataAnalystAgent(ado=board, teams=teams, purview=governance, approvals=approvals, config=config, events=events, llm=llm),
        DataStewardAgent(ado=board, teams=teams, purview=governance, config=config, events=events, llm=llm),
    ]

    return {
        "config": config,
        "board": board,
        "teams": teams,
        "approvals": approvals,
        "governance": governance,
        "events": events,
        "agents": agents,
        "work_item_id": work_item_id,
    }


def run_once(work_item_id="local-1", approval_decision="approved", approval_comments=None):
    harness = build_harness(
        work_item_id=work_item_id,
        approval_decision=approval_decision,
        approval_comments=approval_comments,
    )
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
