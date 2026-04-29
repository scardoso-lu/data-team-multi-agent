from unittest.mock import Mock, patch

from agents.qa_engineer.app import QAEngineerAgent
from config import AppConfig


def fallback_llm():
    return Mock(complete_json=lambda task, payload, fallback=None: fallback)

def test_qa_engineer_agent():
    """Test the QA Engineer Agent workflow."""
    config = AppConfig()
    
    # Mock the skills
    mock_ado = Mock()
    mock_ado.claim_work_item.return_value = "12345"
    mock_ado.update_wiki.return_value = True
    mock_ado.move_work_item.return_value = "12345"
    
    mock_teams = Mock()
    mock_teams.send_approval_request.return_value = True
    
    # Patch the skill loader
    with patch("agents.qa_engineer.app.SkillLoader") as mock_skill_loader:
        mock_loader_instance = Mock()
        mock_loader_instance.get_skill.side_effect = lambda skill_name: {
            "ado_integration": Mock(ADOIntegration=lambda: mock_ado),
            "teams_integration": Mock(TeamsIntegration=lambda: mock_teams),
        }[skill_name]
        mock_skill_loader.return_value = mock_loader_instance
        
        # Initialize the agent
        agent = QAEngineerAgent(llm=fallback_llm())
        
        # Test claiming a work item
        agent.claim_work_item("12345")
        assert agent.work_item_id == "12345"
        mock_ado.claim_work_item.assert_called_once_with("12345")
        
        # Test running data quality checks
        pipelines = {
            "pipelines": config.require("fabric", "pipelines"),
            "business_io_examples": config.require("architecture", "business_io_examples"),
        }
        quality_results = agent.run_data_quality_checks(pipelines)
        assert quality_results["checks"] == config.require("qa", "quality_results")
        assert "acceptance_tests" in quality_results
        assert quality_results["business_io_examples"] == pipelines["business_io_examples"]
        mock_ado.update_wiki.assert_called_once()
        
        # Test requesting approval
        agent.request_approval()
        mock_teams.send_approval_request.assert_called_once()
        
        # Test moving to next column
        agent.move_to_next_column()
        mock_ado.move_work_item.assert_called_once_with(
            "12345",
            config.agent_value("qa_engineer", "next_column")
        )
        
