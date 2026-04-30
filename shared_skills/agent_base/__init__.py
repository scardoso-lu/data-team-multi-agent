import logging
import time
from pathlib import Path

from approvals import APPROVED, REJECTED, TIMED_OUT, new_approval_record
from events import APPROVAL_RECEIVED, APPROVAL_REJECTED, APPROVAL_REQUESTED, APPROVAL_TIMED_OUT
from agent_runtime import WorkItemBlocked, failure_result, retry_operation
from checkpoint import clear_checkpoint, list_stale_checkpoints, write_checkpoint
from config import AppConfig
from events import ARTIFACT_CREATED, WORK_ITEM_CLAIMED, WORK_ITEM_MOVED, build_event_sink
from events import ARTIFACT_CORRECTION_ATTEMPTED
from tools import ToolRegistry


def configure_agent_logger(logger_name, log_file):
    """Create one file+stdout logger per agent module."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class DependencyProvider:
    """Creates concrete shared-skill clients behind a small factory API."""

    SKILL_FACTORIES = {
        "ado": ("ado_integration", "ADOIntegration"),
        "teams": ("teams_integration", "TeamsIntegration"),
        "purview": ("purview_integration", "PurviewIntegration"),
    }

    def __init__(self, skill_loader_cls):
        self.skill_loader = skill_loader_cls()

    def create(self, dependency_name):
        skill_name, factory_name = self.SKILL_FACTORIES[dependency_name]
        module = self.skill_loader.get_skill(skill_name)
        return getattr(module, factory_name)()


class AgentRuntimeMixin:
    """Shared runtime helpers for polling agents."""

    @property
    def agent_name(self):
        return getattr(self, "_agent_name", self.__class__.__name__)

    def wait_for_approval(self, timeout_seconds=None):
        timeout = timeout_seconds or self.runtime_config["approval_timeout_seconds"]
        return self.approvals.wait_for_approval(
            self.work_item_id,
            timeout_seconds=timeout,
            poll_seconds=self.runtime_config["approval_poll_seconds"],
        )

    def artifact_summary(self, artifact_type, artifact):
        return f"{artifact_type} ready for review"

    def artifact_links(self, artifact_type, artifact):
        return []

    def request_human_approval(self, artifact_type, artifact):
        record = new_approval_record(
            work_item_id=self.work_item_id,
            agent=self.agent_config["display_name"],
            stage=self.agent_config["column"],
            artifact_summary=self.artifact_summary(artifact_type, artifact),
            artifact_links=self.artifact_links(artifact_type, artifact),
        )

        if hasattr(self.approvals, "create_approval"):
            record = self.approvals.create_approval(record)

        message = self.agent_config["approval_message"].format(work_item_id=self.work_item_id)
        self.teams.send_approval_request(
            work_item_id=self.work_item_id,
            agent_name=self.agent_config["display_name"],
            message=message,
            approval_id=record["approval_id"],
            artifact_summary=record["artifact_summary"],
            artifact_links=record["artifact_links"],
        )
        self.events.emit(
            APPROVAL_REQUESTED,
            self.agent_name,
            self.work_item_id,
            approval_id=record["approval_id"],
            artifact_summary=record["artifact_summary"],
            artifact_links=record["artifact_links"],
        )
        return record

    def wait_for_approval_decision(self, approval_id):
        if hasattr(self.approvals, "wait_for_decision"):
            return self.approvals.wait_for_decision(
                approval_id,
                timeout_seconds=self.runtime_config["approval_timeout_seconds"],
                poll_seconds=self.runtime_config["approval_poll_seconds"],
            )

        approved = self.wait_for_approval()
        return {
            "approval_id": approval_id,
            "status": APPROVED if approved else TIMED_OUT,
            "decided_by": None,
            "comments": None,
        }

    def route_approval_decision(self, decision):
        status = decision["status"]
        if status == APPROVED:
            self.events.emit(
                APPROVAL_RECEIVED,
                self.agent_name,
                self.work_item_id,
                approval_id=decision["approval_id"],
                decided_by=decision.get("decided_by"),
                comments=decision.get("comments"),
            )
            return "approved", self.agent_config["next_column"]

        if status == REJECTED:
            target_column = self.runtime_config["rework_column"]
            self.ado.move_work_item(self.work_item_id, target_column)
            self.events.emit(
                APPROVAL_REJECTED,
                self.agent_name,
                self.work_item_id,
                approval_id=decision["approval_id"],
                decided_by=decision.get("decided_by"),
                comments=decision.get("comments"),
                to_column=target_column,
            )
            return "rejected", target_column

        target_column = self.runtime_config["approval_timeout_column"]
        self.ado.move_work_item(self.work_item_id, target_column)
        self.events.emit(
            APPROVAL_TIMED_OUT,
            self.agent_name,
            self.work_item_id,
            approval_id=decision["approval_id"],
            to_column=target_column,
        )
        return "timed_out", target_column

    def log_process_result(self, logger, result):
        if result["status"] == "failed":
            logger.error(result)
        else:
            logger.info(result)

    def drain_available_work_items(self, logger):
        while True:
            result = self.process_next_item()
            self.log_process_result(logger, result)
            if result["status"] != "processed":
                return result


class BoardAgent(AgentRuntimeMixin):
    """Template method for agents that process one ADO board column."""

    agent_key = None
    dependency_names = ("ado", "teams")
    requires_approval = True
    artifact_type = None

    def __init__(
        self,
        *,
        config=None,
        events=None,
        approvals=None,
        dependency_provider=None,
        approval_server_cls=None,
        middlewares=None,
        **dependencies,
    ):
        self.config = config or AppConfig()
        self._agent_name = self.agent_key
        self.agent_config = self.config.agent(self.agent_key)
        self.runtime_config = self.config.require("runtime")
        self.events = events or build_event_sink(self.config)
        self.middlewares = list(middlewares or [])
        self.work_item_id = None
        self.tools = ToolRegistry()
        self._register_default_tools()
        self._checkpoint_dir = self.runtime_config.get("checkpoint_dir", "logs/checkpoints")

        provider = dependency_provider
        for dependency_name in self.dependency_names:
            client = dependencies.get(dependency_name)
            if client is None:
                if provider is None:
                    raise ValueError(
                        f"Missing dependency_provider while creating {dependency_name}"
                    )
                client = provider.create(dependency_name)
            setattr(self, dependency_name, client)

        if self.requires_approval:
            if approvals is not None:
                self.approvals = approvals
            elif approval_server_cls is not None:
                self.approvals = approval_server_cls()
            else:
                raise ValueError("approval_server_cls is required for approval-gated agents")

    def claim_work_item(self, work_item_id):
        self.work_item_id = self.ado.claim_work_item(work_item_id)
        print(f"{self.agent_config['display_name']} claimed work item {self.work_item_id}")

    def move_to_next_column(self):
        self.ado.move_work_item(self.work_item_id, self.agent_config["next_column"])

    def get_stage_input(self, work_item_id):
        return self.ado.get_work_item_details(work_item_id)

    def get_candidate_work_items(self):
        work_item_types = self.agent_config.get("work_item_types")
        if work_item_types:
            return self.ado.get_work_items(
                self.agent_config["column"],
                work_item_types=work_item_types,
            )
        return self.ado.get_work_items(self.agent_config["column"])

    def execute_stage(self, stage_input):
        raise NotImplementedError
    def _register_default_tools(self): # noqa: B027
        pass
    def record_memory(self, work_item_id, artifact, result_status):
        return None
    def _run_before_agent(self, context):
        for mw in self.middlewares: context = mw.before_agent(context)
        return context
    def _run_after_agent(self, result, context):
        for mw in reversed(self.middlewares): result = mw.after_agent(result, context)
        return result

    def validate_artifact(self, artifact):
        return artifact

    def correct_artifact(self, artifact, error):
        """Override in concrete agents to re-prompt the LLM with the error."""
        return artifact

    def save_artifact(self, work_item_id, artifact):
        if hasattr(self.ado, "set_work_item_details"):
            self.ado.set_work_item_details(work_item_id, artifact)

    def request_approval(self):
        return self.request_human_approval(self.artifact_type, {})

    def run(self, logger):
        logger.info("%s Agent started", self.agent_config["display_name"])

        while True:
            try:
                logger.info("Polling ADO for new work items...")
                self.drain_available_work_items(logger)
            except Exception as exc:
                logger.error("Error polling ADO for work items: %s", exc, exc_info=True)

            logger.info(
                "Waiting for %s seconds before next poll...",
                self.runtime_config["poll_interval_seconds"],
            )
            time.sleep(self.runtime_config["poll_interval_seconds"])

    def process_next_item(self):
        work_items = self.get_candidate_work_items()
        if not work_items:
            return {
                "agent": self.agent_key,
                "status": "skipped",
                "reason": "no_work_items",
                "column": self.agent_config["column"],
            }

        work_item_id = work_items[0]
        try:
            max_retries = self.runtime_config["max_retries"]
            retry_delay = self.runtime_config["retry_delay_seconds"]
            self.claim_work_item(work_item_id)
            write_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
            self.events.emit(WORK_ITEM_CLAIMED, self.agent_key, work_item_id)

            stage_input = retry_operation(
                lambda: self.get_stage_input(work_item_id),
                max_retries,
                retry_delay,
            )
            self._run_before_agent({"work_item_id": work_item_id, "stage_input": stage_input})
            artifact = retry_operation(
                lambda: self.execute_stage(stage_input),
                max_retries,
                retry_delay,
            )
            max_correction_attempts = self.runtime_config.get("max_correction_attempts", 2)
            for attempt in range(max_correction_attempts + 1):
                try:
                    self.validate_artifact(artifact)
                    break
                except (ValueError, KeyError) as exc:
                    if attempt == max_correction_attempts:
                        raise
                    self.events.emit(
                        ARTIFACT_CORRECTION_ATTEMPTED,
                        self.agent_key,
                        work_item_id,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    artifact = self.correct_artifact(artifact, exc)
            self.save_artifact(work_item_id, artifact)
            self.events.emit(
                ARTIFACT_CREATED,
                self.agent_key,
                work_item_id,
                artifact_type=self.artifact_type,
                artifact=artifact,
            )

            if self.requires_approval:
                approval = self.request_human_approval(self.artifact_type, artifact)
                decision = self.wait_for_approval_decision(approval["approval_id"])
                decision_status, target_column = self.route_approval_decision(decision)

                if decision_status != "approved":
                    return {
                        "agent": self.agent_key,
                        "status": "skipped",
                        "reason": f"approval_{decision_status}",
                        "work_item_id": work_item_id,
                        "moved_to": target_column,
                        "approval": decision,
                    }

            self.move_to_next_column()
            clear_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
            self.events.emit(
                WORK_ITEM_MOVED,
                self.agent_key,
                work_item_id,
                to_column=self.agent_config["next_column"],
            )
            result = {
                "agent": self.agent_key,
                "status": "processed",
                "work_item_id": work_item_id,
                "moved_to": self.agent_config["next_column"],
                "artifact": artifact,
            }
            if hasattr(self, "memory"):
                self.record_memory(work_item_id, artifact, "processed")
            return self._run_after_agent(result, {"work_item_id": work_item_id, "artifact": artifact})
        except WorkItemBlocked as exc:
            clear_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
            return {
                "agent": self.agent_key,
                "status": "skipped",
                "reason": exc.reason,
                "work_item_id": work_item_id,
                "message": exc.message,
            }
        except Exception as exc:
            clear_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
            return failure_result(
                self.agent_key,
                work_item_id,
                exc,
                events=self.events,
                ado=self.ado,
                error_column=self.runtime_config.get("error_column"),
            )
