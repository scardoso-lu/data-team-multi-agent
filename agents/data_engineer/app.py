# Data Engineer Agent
# Prepares Medallion implementation packages for human execution.

from agents.skill_loader import SkillLoader
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import extract_business_io_examples, validate_fabric_artifact
from llm_integration import LocalLLMClient

logger = configure_agent_logger(__name__, "logs/data_engineer/data_engineer.log")

class DataEngineerAgent(BoardAgent):
    """Prepares implementation plans without mutating Fabric resources."""

    agent_key = "data_engineer"
    dependency_names = ("ado", "teams")
    artifact_type = "fabric_implementation"
    
    def __init__(self, ado=None, teams=None, fabric=None, approvals=None, config=None, events=None, llm=None):
        provider = DependencyProvider(SkillLoader) if ado is None or teams is None else None
        self.skill_loader = provider.skill_loader if provider else None
        super().__init__(
            ado=ado,
            teams=teams,
            approvals=approvals,
            config=config,
            events=events,
            dependency_provider=provider,
            approval_server_cls=ApprovalServer,
        )
        self.llm = llm or LocalLLMClient(config=self.config)
    
    def implement_medallion_architecture(self, architecture_doc):
        """Prepare Bronze, Silver, and Gold implementation steps for human execution."""
        logger.info("Preparing Medallion implementation package for work item %s", self.work_item_id)
        business_io_examples = extract_business_io_examples(architecture_doc)
        user_stories = architecture_doc.get("user_stories", [])
        pipeline_names = self.config.require("fabric", "pipelines")
        proposed_workspace = f"{self.agent_config['workspace_prefix']}_{self.work_item_id}"
        implementation_plan = self.llm.complete_json(
            task=(
                "Create a reviewable implementation package for Fabric Bronze, Silver, "
                "and Gold pipelines. Do not create workspaces, deploy pipelines, run "
                "dataflows, or mutate cloud resources. Use the business input/output "
                "examples as acceptance goals for the human engineer. Implement from the "
                "engineer-ready user stories, where each story contains its specification."
            ),
            payload={
                "architecture": architecture_doc,
                "user_stories": user_stories,
                "pipeline_names": pipeline_names,
                "proposed_workspace": proposed_workspace,
            },
            fallback={
                "human_action_required": True,
                "privileged_actions": ["create_workspace", "deploy_pipeline"],
                "proposed_workspace": proposed_workspace,
                "pipelines": pipeline_names,
                "layers": ["bronze", "silver", "gold"],
                "user_stories": user_stories,
                "acceptance_examples": business_io_examples,
            },
        )
        if not isinstance(implementation_plan, dict):
            implementation_plan = {
                "human_action_required": True,
                "privileged_actions": ["create_workspace", "deploy_pipeline"],
                "proposed_workspace": proposed_workspace,
                "pipelines": pipeline_names,
                "layers": ["bronze", "silver", "gold"],
                "user_stories": user_stories,
                "acceptance_examples": business_io_examples,
            }
        implementation_plan["human_action_required"] = True
        implementation_plan["proposed_workspace"] = implementation_plan.get(
            "proposed_workspace",
            proposed_workspace,
        )
        implementation_plan["pipelines"] = implementation_plan.get("pipelines", pipeline_names)
        implementation_plan["privileged_actions"] = implementation_plan.get(
            "privileged_actions",
            ["create_workspace", "deploy_pipeline"],
        )
        logger.info("Prepared human execution package for work item %s", self.work_item_id)
        
        return {
            "execution_mode": "human_required",
            "proposed_workspace": implementation_plan["proposed_workspace"],
            "pipelines": implementation_plan["pipelines"],
            "implementation_plan": implementation_plan,
            "user_stories": implementation_plan.get("user_stories", user_stories),
            "business_io_examples": business_io_examples,
        }
    
    def execute_stage(self, architecture_doc):
        return self.implement_medallion_architecture(architecture_doc)

    def validate_artifact(self, artifact):
        return validate_fabric_artifact(artifact)
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = DataEngineerAgent()
    agent.run()
