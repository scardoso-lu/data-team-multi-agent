from approvals import APPROVED, REJECTED, TIMED_OUT, new_approval_record
from events import APPROVAL_RECEIVED, APPROVAL_REJECTED, APPROVAL_REQUESTED, APPROVAL_TIMED_OUT


class AgentRuntimeMixin:
    """Shared runtime helpers for polling agents."""

    @property
    def agent_name(self):
        return getattr(self, "_agent_name", self.__class__.__name__)

    def approval_callback_url(self, approval_id=None, action="approve"):
        identifier = approval_id or self.work_item_id
        return (
            f"{self.runtime_config['callback_scheme']}://"
            f"{self.agent_config['service_name']}:{self.agent_config['port']}"
            f"/{action}/{identifier}"
        )

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
            callback_url=self.approval_callback_url(record["approval_id"]),
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

    def start_approval_server(self):
        if not hasattr(self, "approvals"):
            return None
        return self.approvals.start(
            host=self.runtime_config["approval_host"],
            port=self.agent_config["port"],
        )

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
