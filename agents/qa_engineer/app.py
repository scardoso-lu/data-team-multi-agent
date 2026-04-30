# QA Engineer Agent
# Evaluates data quality and acceptance criteria from reviewed artifacts.

from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import extract_business_io_examples, validate_quality_artifact
from llm_integration import LocalLLMClient
from memory import AgentMemoryStore
from middleware.context_size import ContextSizeMiddleware
from middleware.memory import MemoryMiddleware
from middleware.pii import PIIScrubbingMiddleware
from middleware.summarisation import SummarisationMiddleware

logger = configure_agent_logger(__name__, "logs/qa_engineer/qa_engineer.log")

class QAEngineerAgent(BoardAgent):
    """Handles data quality checks without mutating platform resources."""

    agent_key = "qa_engineer"
    dependency_names = ("ado", "teams")
    artifact_type = "quality_results"
    
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
    
    def run_data_quality_checks(self, pipelines):
        """Prepare data quality checks from the reviewed implementation package."""
        logger.info("Running data quality checks for work item %s", self.work_item_id)
        business_io_examples = extract_business_io_examples(pipelines)
        
        quality_results = self.config.copy_value("qa", "quality_results", default={})
        acceptance_tests = self.llm.complete_json(
            task=load_task("qa_engineer"),
            payload={
                "fabric_artifact": pipelines,
                "business_io_examples": business_io_examples,
                "fallback_quality_results": quality_results,
            },
            fallback={"checks": quality_results, "examples": business_io_examples},
        )
        if not isinstance(acceptance_tests, dict):
            acceptance_tests = {"checks": quality_results, "examples": business_io_examples}
        artifact = {
            "checks": quality_results,
            "acceptance_tests": acceptance_tests,
            "business_io_examples": business_io_examples,
        }
        
        # Publish test evidence with the acceptance examples QA used.
        self.ado.update_wiki(
            content=str(artifact),
            page_name=f"{self.agent_config['wiki_page_prefix']}_{self.work_item_id}"
        )
        
        return artifact
    
    def execute_stage(self, pipelines):
        return self.run_data_quality_checks(pipelines)

    def validate_artifact(self, artifact):
        return validate_quality_artifact(artifact)

    def correct_artifact(self, artifact, error):
        logger.warning(
            "Artifact validation failed for work item %s: %s. Attempting correction.",
            self.work_item_id,
            error,
        )
        fallback = self.config.copy_value("qa", "quality_results", default={})
        return self.llm.complete_json_with_correction(
            task=load_task("qa_engineer"),
            payload={"fabric_artifact": artifact},
            fallback=fallback,
            previous_response=artifact,
            error=error,
        )
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = QAEngineerAgent()
    agent.run()
