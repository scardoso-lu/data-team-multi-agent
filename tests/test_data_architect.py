import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from unittest.mock import Mock, patch
from agents.data_architect.app import DataArchitectAgent
from config import AppConfig

def test_data_architect_agent():
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
        agent = DataArchitectAgent()
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test designing architecture
        requirements = "Design a customer order system"
        architecture = agent.design_architecture(requirements)
        assert "tables" in architecture
        assert "relationships" in architecture
        assert architecture == config.require("architecture")
        mock_ado.update_wiki.assert_called_once()
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_architect", "next_column")
        )
        
        print("Data Architect Agent tests passed!")

if __name__ == "__main__":
    test_data_architect_agent()
