import subprocess
from pathlib import Path

from agents.registry import agent_names, build_agent
from agents.skill_loader import SkillLoader


def test_registry_builds_each_agent_with_injected_dependencies(monkeypatch):
    created = []

    class FakeProvider:
        def __init__(self, skill_loader_cls):
            self.skill_loader = skill_loader_cls()

        def create(self, dependency_name):
            created.append(dependency_name)
            return object()

    class FakeApprovalServer:
        pass

    monkeypatch.setattr("agents.requirements_analyst.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.data_architect.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.data_engineer.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.qa_engineer.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.data_analyst.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.data_steward.app.DependencyProvider", FakeProvider)
    monkeypatch.setattr("agents.requirements_analyst.app.ApprovalServer", FakeApprovalServer)
    monkeypatch.setattr("agents.data_architect.app.ApprovalServer", FakeApprovalServer)
    monkeypatch.setattr("agents.data_engineer.app.ApprovalServer", FakeApprovalServer)
    monkeypatch.setattr("agents.qa_engineer.app.ApprovalServer", FakeApprovalServer)
    monkeypatch.setattr("agents.data_analyst.app.ApprovalServer", FakeApprovalServer)

    agents = [build_agent(agent_name) for agent_name in agent_names()]

    assert [agent.agent_name for agent in agents] == list(agent_names())
    assert created.count("ado") == len(agent_names())
    assert created.count("teams") == len(agent_names())
    assert created.count("fabric") == 0
    assert created.count("purview") == 2


def test_skill_loader_defaults_to_local_shared_skills():
    loader = SkillLoader()

    assert Path(loader.skills_dir).name == "shared_skills"
    assert loader.get_skill("events").WORK_ITEM_CLAIMED == "work_item_claimed"


def test_setup_script_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", "setup.sh"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_setup_script_rejects_unknown_agent():
    result = subprocess.run(
        ["bash", "setup.sh", "unknown_agent"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Unknown agent: unknown_agent" in result.stderr
    assert "Valid agents:" in result.stderr
