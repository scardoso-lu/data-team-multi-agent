# Data Steward Agent
# Acts as the final gatekeeper for data governance and compliance.

from agents.skill_loader import SkillLoader
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import validate_governance_artifact
from llm_integration import LocalLLMClient

logger = configure_agent_logger(__name__, "logs/data_steward/data_steward.log")

class DataStewardAgent(BoardAgent):
    """Handles final governance review and compliance checks."""

    agent_key = "data_steward"
    dependency_names = ("ado", "teams", "purview")
    requires_approval = False
    artifact_type = "audit_results"
    
    def __init__(self, ado=None, teams=None, purview=None, config=None, events=None, llm=None):
        provider = DependencyProvider(SkillLoader) if ado is None or teams is None or purview is None else None
        self.skill_loader = provider.skill_loader if provider else None
        super().__init__(
            ado=ado,
            teams=teams,
            purview=purview,
            config=config,
            events=events,
            dependency_provider=provider,
        )
        self.llm = llm or LocalLLMClient(config=self.config)
    
    def audit_lifecycle(self):
        """Audit the entire data lifecycle for compliance."""
        logger.info("Auditing data lifecycle for work item %s", self.work_item_id)
        
        fallback = self.config.copy_value("governance", "audit_results", default={})
        audit_results = self.llm.complete_json(
            task=(
                "Review the lifecycle artifact for governance, compliance, security, "
                "and production-data safety. Return a governance audit result."
            ),
            payload={
                "work_item_id": self.work_item_id,
                "fallback_audit_results": fallback,
            },
            fallback=fallback,
        )
        if not isinstance(audit_results, dict):
            audit_results = fallback
        
        self.purview.publish_metadata(audit_results)
        
        # Keep the ticket discussion sanitized; detailed evidence remains in governed artifacts.
        self.teams.send_notification(
            title=self.agent_config["completion_title"].format(work_item_id=self.work_item_id),
            message=self.agent_config["completion_message"].format(work_item_id=self.work_item_id),
            work_item_id=self.work_item_id,
        )
        
        return audit_results
    
    def execute_stage(self, stage_input):
        return self.audit_lifecycle()

    def mark_as_done(self):
        self.move_to_next_column()

    def validate_artifact(self, artifact):
        return validate_governance_artifact(artifact)
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = DataStewardAgent()
    agent.run()
