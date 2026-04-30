# Data Architect Agent
# Translates business requirements into data models and scaffolding.

import json
from pathlib import Path

from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from artifacts import (
    build_default_user_stories,
    build_exploration_business_io_examples,
    normalize_user_stories,
    validate_architecture_artifact,
    validate_requirements_artifact,
    validate_user_stories,
)
from llm_integration import LocalLLMClient
from memory import AgentMemoryStore
from middleware.context_size import ContextSizeMiddleware
from middleware.memory import MemoryMiddleware
from middleware.pii import PIIScrubbingMiddleware
from middleware.summarisation import SummarisationMiddleware

logger = configure_agent_logger(__name__, "logs/data_architect/data_architect.log")

SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "pat",
    "key",
)

class DataArchitectAgent(BoardAgent):
    """Handles architecture design and repository scaffolding."""

    agent_key = "data_architect"
    dependency_names = ("ado", "teams")
    artifact_type = "architecture"
    
    def __init__(self, ado=None, teams=None, approvals=None, config=None, events=None, llm=None):
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
        self.debug_specs_path = Path("logs/data_architect/latest_specs.json")
        self.debug_work_item_path = Path("logs/data_architect/latest_work_item.json")

    def child_work_item_type(self):
        process = self.config.copy_value("ado", "process", default="Agile")
        by_process = self.config.copy_value(
            "ado",
            "child_work_item_type_by_process",
            default={},
        )
        return by_process.get(process, by_process.get("Agile", "User Story"))

    def create_engineering_children(self, parent_work_item_id, user_stories):
        if not hasattr(self.ado, "create_child_work_item"):
            return []

        child_type = self.child_work_item_type()
        children = []
        for story in user_stories:
            child_id = self.ado.create_child_work_item(
                parent_work_item_id=parent_work_item_id,
                work_item_type=child_type,
                story=story,
                target_column=self.agent_config["next_column"],
            )
            children.append(
                {
                    "id": child_id,
                    "type": child_type,
                    "title": story["title"],
                    "target_column": self.agent_config["next_column"],
                }
            )
        return children

    def existing_description_from_requirements(self, requirements):
        fields = requirements.get("fields", {}) if isinstance(requirements, dict) else {}
        for source in (fields, requirements):
            if not isinstance(source, dict):
                continue
            for key in ("System.Description", "Description", "description"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def post_specs_to_current_work_item(self, architecture_doc, requirements):
        if not hasattr(self.ado, "post_work_item_specification"):
            return None
        return self.ado.post_work_item_specification(
            self.work_item_id,
            architecture_doc,
            existing_description=self.existing_description_from_requirements(requirements),
        )

    def update_architecture_wiki(self, architecture_doc):
        try:
            self.ado.update_wiki(
                content=str(architecture_doc),
                page_name=f"{self.agent_config['wiki_page_prefix']}_{self.work_item_id}"
            )
        except Exception as exc:
            logger.warning(
                "Skipping architecture wiki update for work item %s: %s",
                self.work_item_id,
                exc,
            )

    def write_debug_specs(self, architecture_doc):
        """Write latest generated architect specifications for local debugging."""
        self.debug_specs_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_specs_path.write_text(
            json.dumps(
                {
                    "work_item_id": self.work_item_id,
                    "source_work_item_type": architecture_doc.get("source_work_item_type"),
                    "child_work_items": architecture_doc.get("child_work_items", []),
                    "user_stories": architecture_doc.get("user_stories", []),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def redact_debug_value(self, value):
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                    redacted[key] = "<redacted>"
                else:
                    redacted[key] = self.redact_debug_value(item)
            return redacted
        if isinstance(value, list):
            return [self.redact_debug_value(item) for item in value]
        return value

    def write_debug_work_item(self, work_item):
        """Write the latest fetched work item payload for local debugging."""
        self.debug_work_item_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_work_item_path.write_text(
            json.dumps(
                {
                    "work_item_id": self.work_item_id,
                    "work_item": self.redact_debug_value(work_item),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    
    def design_architecture(self, requirements_artifact):
        """Translate a validated requirements artifact into engineer-ready specs."""
        logger.info("Designing architecture for work item %s", self.work_item_id)
        requirements_artifact = validate_requirements_artifact(requirements_artifact)
        requirements = requirements_artifact["original_work_item"]
        self.write_debug_work_item(requirements)

        business_io_examples = requirements_artifact.get("business_io_examples", [])
        if requirements_artifact["is_exploration"] and not business_io_examples:
            business_io_examples = build_exploration_business_io_examples(requirements)
            self.teams.send_notification(
                title=f"Work Item {self.work_item_id} Exploration Fallback Applied",
                message=(
                    "No business input/output examples were provided, but the work "
                    "item is human-confirmed as an exploration topic. The Architect "
                    "will generate exploratory specifications and the human reviewer "
                    "must validate the specs and plan before Engineering proceeds."
                ),
                work_item_id=self.work_item_id,
            )

        fallback = self.config.copy_value("architecture", default={})
        fallback["user_stories"] = build_default_user_stories(
            requirements,
            business_io_examples,
        )
        fallback["business_io_examples"] = business_io_examples
        supports_tao = callable(getattr(self.llm, "run_tao_loop", None)) and "run_tao_loop" in getattr(type(self.llm), "__dict__", {})
        if supports_tao:
            architecture_doc = self.llm.run_tao_loop(
                task=load_task("data_architect"),
                payload={
                    "requirements": requirements_artifact,
                    "fallback_contract": fallback,
                },
                tool_registry=self.tools,
                fallback=fallback,
                max_steps=6,
            )
        else:
            architecture_doc = self.llm.complete_json(
                task=load_task("data_architect"),
                payload={
                    "requirements": requirements_artifact,
                    "fallback_contract": fallback,
                },
                fallback=fallback,
            )
        if not isinstance(architecture_doc, dict):
            architecture_doc = fallback
        else:
            architecture_doc = {**fallback, **architecture_doc}
        architecture_doc["business_io_examples"] = business_io_examples
        if requirements_artifact["is_exploration"]:
            architecture_doc["exploration_mode"] = True
            architecture_doc["requires_human_spec_validation"] = True
            architecture_doc["exploration_note"] = (
                "Business examples were not supplied. These exploratory examples and "
                "the resulting specs/plan require human validation before Engineering."
            )
        if "user_stories" not in architecture_doc:
            architecture_doc["user_stories"] = build_default_user_stories(
                requirements,
                business_io_examples,
            )
        architecture_doc["user_stories"] = normalize_user_stories(
            architecture_doc["user_stories"]
        )
        validate_user_stories(architecture_doc["user_stories"], "architecture user_stories")
        source_work_item_type = requirements_artifact["work_item_type"]
        architecture_doc["source_work_item_type"] = source_work_item_type
        architecture_doc["child_work_items"] = []
        self.write_debug_specs(architecture_doc)
        if requirements_artifact["is_parent"]:
            architecture_doc["child_work_items"] = self.create_engineering_children(
                self.work_item_id,
                architecture_doc["user_stories"],
            )
            self.write_debug_specs(architecture_doc)
        else:
            self.post_specs_to_current_work_item(architecture_doc, requirements)
        
        # The architecture artifact is the downstream contract for implementation and QA.
        self.update_architecture_wiki(architecture_doc)
        
        return architecture_doc
    
    def execute_stage(self, stage_input):
        return self.design_architecture(stage_input)

    def validate_artifact(self, artifact):
        return validate_architecture_artifact(artifact)

    def correct_artifact(self, artifact, error):
        logger.warning(
            "Artifact validation failed for work item %s: %s. Attempting correction.",
            self.work_item_id,
            error,
        )
        fallback = self.config.copy_value("architecture", default={})
        return self.llm.complete_json_with_correction(
            task=load_task("data_architect"),
            payload={"requirements": artifact},
            fallback=fallback,
            previous_response=artifact,
            error=error,
        )

    def record_memory(self, work_item_id, artifact, result_status):
        self.memory.update(
            f"work_item_{work_item_id}_stories",
            f"Generated {len(artifact.get('user_stories', []))} user stories with status={result_status}",
        )
    
    def run(self):
        """Main agent loop."""
        super().run(logger)

if __name__ == "__main__":
    agent = DataArchitectAgent()
    agent.run()
