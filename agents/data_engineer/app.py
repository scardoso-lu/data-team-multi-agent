# Data Engineer Agent
# Prepares Medallion implementation packages for human execution.

from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import extract_business_io_examples, validate_fabric_artifact
from llm_integration import LocalLLMClient
from memory import AgentMemoryStore
from middleware.context_size import ContextSizeMiddleware
from middleware.memory import MemoryMiddleware
from middleware.pii import PIIScrubbingMiddleware
from middleware.summarisation import SummarisationMiddleware

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
        self.memory = AgentMemoryStore(f"logs/memory/{self.agent_key}/memory.json")
        llm_middlewares = [MemoryMiddleware(self.memory), PIIScrubbingMiddleware(), ContextSizeMiddleware(config=self.config)]
        self.llm = llm or LocalLLMClient(config=self.config, events=self.events, agent=self.agent_key, middlewares=llm_middlewares)
        if hasattr(self.llm, "middlewares"):
            self.llm.middlewares.append(SummarisationMiddleware(config=self.config, llm=self.llm))
    
    def implement_medallion_architecture(self, architecture_doc):
        """Prepare Bronze, Silver, and Gold implementation steps for human execution."""
        logger.info("Preparing Medallion implementation package for work item %s", self.work_item_id)
        business_io_examples = extract_business_io_examples(architecture_doc)
        user_stories = architecture_doc.get("user_stories", [])
        pipeline_names = self.config.require("fabric", "pipelines")
        proposed_workspace = f"{self.agent_config['workspace_prefix']}_{self.work_item_id}"
        fallback_plan = {
            "human_action_required": True,
            "privileged_actions": ["create_workspace", "deploy_pipeline"],
            "proposed_workspace": proposed_workspace,
            "pipelines": pipeline_names,
            "layers": ["bronze", "silver", "gold"],
            "user_stories": user_stories,
            "acceptance_examples": business_io_examples,
        }
        supports_tao = callable(getattr(self.llm, "run_tao_loop", None)) and "run_tao_loop" in getattr(type(self.llm), "__dict__", {})
        if supports_tao:
            implementation_plan = self.llm.run_tao_loop(
                task=load_task("data_engineer"),
                payload={
                    "architecture": architecture_doc,
                    "user_stories": user_stories,
                    "pipeline_names": pipeline_names,
                    "proposed_workspace": proposed_workspace,
                },
                tool_registry=self.tools,
                fallback=fallback_plan,
                max_steps=6,
            )
        else:
            implementation_plan = self.llm.complete_json(
                task=load_task("data_engineer"),
                payload={
                    "architecture": architecture_doc,
                    "user_stories": user_stories,
                    "pipeline_names": pipeline_names,
                    "proposed_workspace": proposed_workspace,
                },
                fallback=fallback_plan,
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

    def correct_artifact(self, artifact, error):
        logger.warning(
            "Artifact validation failed for work item %s: %s. Attempting correction.",
            self.work_item_id,
            error,
        )
        fallback = self.config.copy_value("fabric", default={})
        return self.llm.complete_json_with_correction(
            task=load_task("data_engineer"),
            payload={"architecture": artifact},
            fallback=fallback,
            previous_response=artifact,
            error=error,
        )
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = DataEngineerAgent()
    agent.run()
