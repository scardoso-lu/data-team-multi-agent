import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from unittest.mock import Mock, patch
from agents.data_analyst.app import DataAnalystAgent
from config import AppConfig

def test_data_analyst_agent():
    """Test the Data Analyst Agent workflow."""
    config = AppConfig()
    
    # Mock the skills
    mock_ado = Mock()
    mock_ado.claim_work_item.return_value = "12345"
    mock_ado.update_wiki.return_value = True
    mock_ado.move_work_item.return_value = "12345"
    
    mock_teams = Mock()
    mock_teams.send_approval_request.return_value = True
    
    mock_purview = Mock()
    mock_purview.publish_metadata.return_value = True
    
    # Patch the skill loader
    with patch("agents.data_analyst.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams),
            "purview_integration": Mock(PurviewIntegration=lambda: mock_purview)
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = DataAnalystAgent()
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test developing semantic model
        gold_layer_schema = {
            "tables": ["customers", "orders", "products"],
            "columns": {
                "customers": ["id", "name", "email"],
                "orders": ["id", "customer_id", "product_id", "amount"],
                "products": ["id", "name", "price"]
            }
        }
        semantic_model = agent.develop_semantic_model(gold_layer_schema)
        assert semantic_model == config.require("semantic_model")
        mock_purview.publish_metadata.assert_called_once()
        mock_ado.update_wiki.assert_called_once()
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_analyst", "next_column")
        )
        
        print("Data Analyst Agent tests passed!")

if __name__ == "__main__":
    test_data_analyst_agent()
