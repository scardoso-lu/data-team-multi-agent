from unittest.mock import Mock, patch

from agents.data_engineer.app import DataEngineerAgent
from config import AppConfig


def fallback_llm():
    return Mock(complete_json=lambda task, payload, fallback=None: fallback)


def test_data_engineer_agent():
    """Test the Data Engineer Agent workflow."""
    config = AppConfig()
    pipelines = config.require("fabric", "pipelines")
    
    # Mock the skills
    mock_ado = Mock()
    mock_ado.claim_work_item.return_value = "12345"
    mock_ado.move_work_item.return_value = "12345"
    
    mock_teams = Mock()
    mock_teams.send_approval_request.return_value = True
    
    # Patch the skill loader
    with patch("agents.data_engineer.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams),
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = DataEngineerAgent(llm=fallback_llm())
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test implementing Medallion architecture
        architecture_doc = {
            "tables": ["customers", "orders", "products"],
            "relationships": {
                "orders": {
                    "customer_id": "customers.id",
                    "product_id": "products.id"
                }
            },
            "user_stories": config.require("architecture", "user_stories"),
            "business_io_examples": config.require("architecture", "business_io_examples"),
        }
        implementation = agent.implement_medallion_architecture(architecture_doc)
        assert implementation["execution_mode"] == "human_required"
        assert implementation["proposed_workspace"] == "workspace_12345"
        assert implementation["pipelines"] == pipelines
        assert "implementation_plan" in implementation
        assert implementation["implementation_plan"]["human_action_required"] is True
        assert implementation["user_stories"] == architecture_doc["user_stories"]
        assert implementation["business_io_examples"] == architecture_doc["business_io_examples"]
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_engineer", "next_column")
        )
        
