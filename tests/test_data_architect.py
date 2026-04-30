import json
from unittest.mock import Mock, patch

from agents.data_architect.app import DataArchitectAgent
from config import AppConfig


def fallback_llm():
    return Mock(complete_json=lambda task, payload, fallback=None: fallback)


def partial_llm(response):
    return Mock(complete_json=lambda task, payload, fallback=None: response)


def requirements_artifact(work_item, work_item_type="Issue", is_parent=False, is_exploration=False):
    return {
        "work_item_type": work_item_type,
        "is_parent": is_parent,
        "is_exploration": is_exploration,
        "business_io_examples": work_item.get("business_io_examples", []),
        "requirements_summary": work_item.get("title")
        or work_item.get("description")
        or work_item.get("fields", {}).get("System.Title")
        or "Requirements summary",
        "original_work_item": work_item,
    }


def test_data_architect_agent(tmp_path):
    """Test the Data Architect Agent workflow."""
    config = AppConfig()
    
    # Mock the skills
    mock_ado = Mock()
    mock_ado.claim_work_item.return_value = "12345"
    mock_ado.update_wiki.return_value = True
    mock_ado.move_work_item.return_value = "12345"
    
    mock_teams = Mock()
    mock_teams.send_approval_request.return_value = True
    
    # Patch the skill loader
    with patch("agents.data_architect.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams)
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = DataArchitectAgent(llm=fallback_llm())
        agent.debug_specs_path = tmp_path / "latest_specs.json"
        agent.debug_work_item_path = tmp_path / "latest_work_item.json"
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test designing architecture
        requirements = {
            "description": "Design a customer order system",
            "business_io_examples": config.require("architecture", "business_io_examples"),
        }
        architecture = agent.design_architecture(requirements_artifact(requirements))
        assert "tables" in architecture
        assert "relationships" in architecture
        assert "user_stories" in architecture
        assert "business_io_examples" in architecture
        assert "flowchart LR" in architecture["user_stories"][0]["specification"]
        assert "## Steps" in architecture["user_stories"][0]["specification"]
        assert architecture["user_stories"][0]["acceptance_criteria"][0]["done"] == ""
        assert architecture["child_work_items"] == []
        mock_ado.post_work_item_specification.assert_called_once()
        mock_ado.update_wiki.assert_called_once()
        debug_work_item = json.loads(agent.debug_work_item_path.read_text(encoding="utf-8"))
        assert debug_work_item["work_item"]["description"] == "Design a customer order system"
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_architect", "next_column")
        )
        

def test_data_architect_creates_children_for_epic_or_feature(tmp_path):
    config = AppConfig()
    mock_ado = Mock()
    mock_ado.create_child_work_item.return_value = "child-1"
    mock_ado.update_wiki.return_value = True
    agent = DataArchitectAgent(
        ado=mock_ado,
        teams=Mock(),
        approvals=Mock(),
        config=config,
        llm=fallback_llm(),
    )
    agent.work_item_id = "feature-1"
    debug_specs_path = tmp_path / "latest_specs.json"
    agent.debug_specs_path = debug_specs_path
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    work_item = {
        "work_item_type": "Feature",
        "title": "Feature work",
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }
    architecture = agent.design_architecture(
        requirements_artifact(work_item, work_item_type="Feature", is_parent=True)
    )

    assert architecture["source_work_item_type"] == "Feature"
    assert architecture["child_work_items"][0]["id"] == "child-1"
    mock_ado.create_child_work_item.assert_called_once()
    assert mock_ado.create_child_work_item.call_args.kwargs["work_item_type"] == "User Story"
    mock_ado.post_work_item_specification.assert_not_called()
    debug_specs = json.loads(debug_specs_path.read_text(encoding="utf-8"))
    assert debug_specs["work_item_id"] == "feature-1"
    assert debug_specs["user_stories"][0]["title"]


def test_data_architect_does_not_create_children_for_user_story_or_issue(tmp_path):
    config = AppConfig()
    mock_ado = Mock()
    mock_ado.update_wiki.return_value = True
    agent = DataArchitectAgent(
        ado=mock_ado,
        teams=Mock(),
        approvals=Mock(),
        config=config,
        llm=fallback_llm(),
    )
    agent.work_item_id = "story-1"
    agent.debug_specs_path = tmp_path / "latest_specs.json"
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    work_item = {
        "work_item_type": "User Story",
        "title": "Story work",
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }
    architecture = agent.design_architecture(
        requirements_artifact(work_item, work_item_type="User Story")
    )

    assert architecture["source_work_item_type"] == "User Story"
    assert architecture["child_work_items"] == []
    mock_ado.create_child_work_item.assert_not_called()
    mock_ado.post_work_item_specification.assert_called_once_with(
        "story-1",
        architecture,
        existing_description="",
    )


def test_data_architect_posts_specs_to_basic_issue_without_children(tmp_path):
    config = AppConfig()
    mock_ado = Mock()
    mock_ado.update_wiki.return_value = True
    agent = DataArchitectAgent(
        ado=mock_ado,
        teams=Mock(),
        approvals=Mock(),
        config=config,
        llm=fallback_llm(),
    )
    agent.work_item_id = 1098
    agent.debug_specs_path = tmp_path / "latest_specs.json"
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    work_item = {
        "fields": {
            "System.WorkItemType": "Issue",
            "System.Title": "Issue work",
            "System.Description": "Calculate issue-specific data quality outputs.",
        },
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }
    architecture = agent.design_architecture(requirements_artifact(work_item))

    assert architecture["source_work_item_type"] == "Issue"
    assert "Calculate issue-specific" in architecture["user_stories"][0]["specification"]
    assert "flowchart LR" in architecture["user_stories"][0]["specification"]
    assert architecture["child_work_items"] == []
    mock_ado.create_child_work_item.assert_not_called()
    mock_ado.post_work_item_specification.assert_called_once_with(
        1098,
        architecture,
        existing_description="Calculate issue-specific data quality outputs.",
    )


def test_data_architect_preserves_fallback_tables_when_llm_returns_partial_doc(tmp_path):
    config = AppConfig()
    mock_ado = Mock()
    mock_ado.update_wiki.return_value = True
    agent = DataArchitectAgent(
        ado=mock_ado,
        teams=Mock(),
        approvals=Mock(),
        config=config,
        llm=partial_llm(
            {
                "user_stories": [
                    {
                        "title": "Partial story",
                        "user_story": "As a data engineer, I want a partial LLM story.",
                        "specification": "INPUT: work item.\nOUTPUT: implementation plan.",
                        "acceptance_criteria": [{"done": "", "item": "Plan is reviewable."}],
                    }
                ]
            }
        ),
    )
    agent.work_item_id = 1098
    agent.debug_specs_path = tmp_path / "latest_specs.json"
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    work_item = {
        "fields": {
            "System.WorkItemType": "Issue",
            "System.Title": "Issue work",
            "System.Description": "Calculate issue-specific data quality outputs.",
        },
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }
    architecture = agent.design_architecture(requirements_artifact(work_item))

    assert architecture["tables"] == config.require("architecture", "tables")
    assert architecture["relationships"] == config.require("architecture", "relationships")
    assert architecture["user_stories"][0]["title"] == "Partial story"
    agent.validate_artifact(architecture)


def test_data_architect_wiki_update_failure_is_not_fatal(tmp_path):
    config = AppConfig()
    mock_ado = Mock()
    mock_ado.update_wiki.side_effect = RuntimeError("wiki not configured")
    agent = DataArchitectAgent(
        ado=mock_ado,
        teams=Mock(),
        approvals=Mock(),
        config=config,
        llm=fallback_llm(),
    )
    agent.work_item_id = "story-1"
    agent.debug_specs_path = tmp_path / "latest_specs.json"
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    work_item = {
        "work_item_type": "Issue",
        "title": "Story work",
        "business_io_examples": config.require("architecture", "business_io_examples"),
    }
    architecture = agent.design_architecture(requirements_artifact(work_item))

    assert architecture["source_work_item_type"] == "Issue"
    mock_ado.post_work_item_specification.assert_called_once()


def test_data_architect_debug_work_item_redacts_sensitive_fields(tmp_path):
    agent = DataArchitectAgent(
        ado=Mock(),
        teams=Mock(),
        approvals=Mock(),
        config=AppConfig(),
        llm=fallback_llm(),
    )
    agent.work_item_id = "secret-1"
    agent.debug_work_item_path = tmp_path / "latest_work_item.json"

    agent.write_debug_work_item(
        {
            "fields": {
                "System.Title": "Safe title",
                "Custom.Token": "do-not-log",
                "Nested": {"api_key": "do-not-log"},
            }
        }
    )

    debug_work_item = json.loads(agent.debug_work_item_path.read_text(encoding="utf-8"))
    fields = debug_work_item["work_item"]["fields"]
    assert fields["System.Title"] == "Safe title"
    assert fields["Custom.Token"] == "<redacted>"
    assert fields["Nested"]["api_key"] == "<redacted>"
