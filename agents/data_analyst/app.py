# Data Analyst Agent
# Develops semantic models and Power BI artifacts based on the Gold layer.

from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import extract_business_io_examples, validate_semantic_model_artifact
from llm_integration import LocalLLMClient
from memory import AgentMemoryStore
from middleware.context_size import ContextSizeMiddleware
from middleware.memory import MemoryMiddleware
from middleware.pii import PIIScrubbingMiddleware
from middleware.summarisation import SummarisationMiddleware

logger = configure_agent_logger(__name__, "logs/data_analyst/data_analyst.log")

class DataAnalystAgent(BoardAgent):
    """Handles semantic modeling and Power BI development."""

    agent_key = "data_analyst"
    dependency_names = ("ado", "teams", "purview")
    artifact_type = "semantic_model"
    
    def __init__(self, ado=None, teams=None, purview=None, approvals=None, config=None, events=None, llm=None):
        provider = DependencyProvider(SkillLoader) if ado is None or teams is None or purview is None else None
        self.skill_loader = provider.skill_loader if provider else None
        super().__init__(
            ado=ado,
            teams=teams,
            purview=purview,
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
    
    def develop_semantic_model(self, gold_layer_schema):
        """Develop a semantic model based on the Gold layer."""
        logger.info("Developing semantic model for work item %s", self.work_item_id)
        business_io_examples = extract_business_io_examples(gold_layer_schema)
        
        fallback = self.config.copy_value("semantic_model", default={})
        semantic_model = self.llm.complete_json(
            task=load_task("data_analyst"),
            payload={
                "gold_layer_schema": gold_layer_schema,
                "fallback_semantic_model": fallback,
            },
            fallback=fallback,
        )
        if not isinstance(semantic_model, dict):
            semantic_model = fallback
        semantic_model["business_io_examples"] = business_io_examples
        
        self.purview.publish_metadata(semantic_model)
        
        # Publish reviewed semantic definitions for governance audit.
        self.ado.update_wiki(
            content=str(semantic_model),
            page_name=f"{self.agent_config['wiki_page_prefix']}_{self.work_item_id}"
        )
        
        return semantic_model
    
    def execute_stage(self, gold_layer_schema):
        return self.develop_semantic_model(gold_layer_schema)

    def validate_artifact(self, artifact):
        return validate_semantic_model_artifact(artifact)

    def correct_artifact(self, artifact, error):
        logger.warning(
            "Artifact validation failed for work item %s: %s. Attempting correction.",
            self.work_item_id,
            error,
        )
        fallback = self.config.copy_value("semantic_model", default={})
        return self.llm.complete_json_with_correction(
            task=load_task("data_analyst"),
            payload={"gold_layer_schema": artifact},
            fallback=fallback,
            previous_response=artifact,
            error=error,
        )
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = DataAnalystAgent()
    agent.run()
