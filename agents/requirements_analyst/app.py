# Requirements Analyst Agent
# Validates, classifies, and enriches work items before architecture begins.

from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from agent_runtime import WorkItemBlocked
from artifacts import (
    extract_business_io_examples,
    is_human_confirmed_exploration,
    is_parent_work_item_type,
    validate_requirements_artifact,
    work_item_type_from_details,
)
from llm_integration import LocalLLMClient

logger = configure_agent_logger(__name__, "logs/requirements_analyst/requirements_analyst.log")


class RequirementsAnalystAgent(BoardAgent):
    """Validates and classifies work items before handing them to the architect."""

    agent_key = "requirements_analyst"
    dependency_names = ("ado", "teams")
    artifact_type = "requirements"

    def __init__(self, ado=None, teams=None, approvals=None, config=None, events=None, llm=None):
        provider = DependencyProvider(SkillLoader) if ado is None or teams is None else None
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

    def analyse_requirements(self, work_item):
        work_item_type = work_item_type_from_details(work_item)
        is_parent = is_parent_work_item_type(work_item_type)
        is_exploration = is_human_confirmed_exploration(work_item)

        try:
            examples = extract_business_io_examples(work_item)
        except ValueError as exc:
            if not is_exploration:
                self.teams.send_notification(
                    title=f"Work Item {self.work_item_id} Needs Business Examples",
                    message=(
                        "Business input/output examples are required before requirements "
                        f"analysis can proceed. Validation error: {exc}"
                    ),
                    work_item_id=self.work_item_id,
                )
                raise WorkItemBlocked("missing_business_io_examples", str(exc)) from exc
            examples = []

        summary = self.llm.complete_json(
            task=load_task("requirements_analyst"),
            payload={"work_item": work_item},
            fallback={"requirements_summary": str(work_item.get("title", ""))},
        )

        requirements_summary = (summary or {}).get(
            "requirements_summary",
            str(work_item.get("title", "")),
        )

        logger.info(
            "Requirements analysis complete for work item %s: type=%s is_parent=%s is_exploration=%s",
            self.work_item_id, work_item_type, is_parent, is_exploration,
        )

        return {
            "work_item_type": work_item_type,
            "is_parent": is_parent,
            "is_exploration": is_exploration,
            "business_io_examples": examples,
            "requirements_summary": requirements_summary,
            "original_work_item": work_item,
        }

    def execute_stage(self, work_item):
        return self.analyse_requirements(work_item)

    def validate_artifact(self, artifact):
        return validate_requirements_artifact(artifact)

    def run(self):
        super().run(logger)


if __name__ == "__main__":
    agent = RequirementsAnalystAgent()
    agent.run()
