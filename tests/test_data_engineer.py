import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from unittest.mock import Mock, patch
from agents.data_engineer.app import DataEngineerAgent
from config import AppConfig


class NamedResource:
    def __init__(self, name):
        self.name = name


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
    
    mock_fabric = Mock()
    mock_fabric.create_workspace.return_value = NamedResource("workspace_12345")
    mock_fabric.deploy_pipeline.side_effect = [
        NamedResource(pipeline_name) for pipeline_name in pipelines
    ]
    
    # Patch the skill loader
    with patch("agents.data_engineer.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams),
            "fabric_integration": Mock(FabricIntegration=lambda: mock_fabric)
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = DataEngineerAgent()
        
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
            }
        }
        implementation = agent.implement_medallion_architecture(architecture_doc)
        assert "workspace" in implementation
        assert implementation["pipelines"] == pipelines
        mock_fabric.create_workspace.assert_called_once()
        assert mock_fabric.deploy_pipeline.call_count == 3
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_engineer", "next_column")
        )
        
        print("Data Engineer Agent tests passed!")

if __name__ == "__main__":
    test_data_engineer_agent()
