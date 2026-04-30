import json

from agents.data_architect.app import DataArchitectAgent
from artifact_types import ArchitectureArtifact
from harness.fakes import FakeApprovalClient, FakeBoardClient, FakeNotificationClient


class FallbackLLM:
    def complete_json(self, task, payload, fallback=None):
        return fallback


def test_board_agent_registers_default_tools():
    agent = DataArchitectAgent(
        ado=FakeBoardClient(columns={}),
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        llm=FallbackLLM(),
    )
    schemas = agent.tools.schema_list()
    names = {schema["name"] for schema in schemas}
    assert {"get_work_item_details", "post_comment", "read_artifact"} <= names


def test_get_work_item_details_tool_dispatch_returns_json():
    board = FakeBoardClient(columns={}, details={"123": {"x": 1}})
    agent = DataArchitectAgent(
        ado=board,
        teams=FakeNotificationClient(),
        approvals=FakeApprovalClient(),
        llm=FallbackLLM(),
    )
    payload = agent.tools.dispatch("get_work_item_details", {"work_item_id": "123"})
    assert json.loads(payload)["x"] == 1


def test_artifact_typed_dict_importable():
    artifact: ArchitectureArtifact = {"tables": ["t1"], "relationships": {}}
    assert artifact["tables"] == ["t1"]
