from unittest.mock import Mock, patch

from agents.data_steward.app import DataStewardAgent
from config import AppConfig


def fallback_llm():
    return Mock(complete_json=lambda task, payload, fallback=None: fallback)

def test_data_steward_agent():
    """Test the Data Steward Agent workflow."""
    config = AppConfig()
    
    # Mock the skills
    mock_ado = Mock()
    mock_ado.claim_work_item.return_value = "12345"
    mock_ado.move_work_item.return_value = "12345"
    
    mock_teams = Mock()
    mock_teams.send_notification.return_value = True
    
    mock_purview = Mock()
    mock_purview.publish_metadata.return_value = True
    
    # Patch the skill loader
    with patch("agents.data_steward.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams),
            "purview_integration": Mock(PurviewIntegration=lambda: mock_purview)
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = DataStewardAgent(llm=fallback_llm())
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test auditing lifecycle
        audit_results = agent.audit_lifecycle()
        assert audit_results == config.require("governance", "audit_results")
        mock_purview.publish_metadata.assert_called_once()
        mock_teams.send_notification.assert_called_once()
        assert mock_teams.send_notification.call_args.kwargs["work_item_id"] == "12345"
        
        # Test marking as done
        agent.mark_as_done()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("data_steward", "next_column")
        )
        
