# DevOps Discussion Integration Skill
# Keeps the legacy TeamsIntegration name while writing notifications to ADO.

import re

from ado_integration import ADOIntegration


class TeamsIntegration:
    """Writes approval requests and status notifications to ADO work item history."""

    def __init__(self, ado=None):
        self.ado = ado or ADOIntegration()

    def format_approval_comment(
        self,
        agent_name,
        message,
        approval_id=None,
        artifact_summary=None,
        artifact_links=None,
    ):
        artifact_links = artifact_links or []
        lines = [
            f"Approval request from {agent_name}",
            "",
            message,
        ]
        if approval_id:
            lines.extend(
                [
                    "",
                    f"Approval ID: {approval_id}",
                    "Set this approval record to approved or rejected in the approval store.",
                ]
            )
        if artifact_summary:
            lines.extend(["", f"Artifact: {artifact_summary}"])
        if artifact_links:
            lines.extend(["", "Links:"])
            for link in artifact_links:
                lines.append(f"- {link.get('label', link.get('url'))}: {link.get('url')}")
        return "\n".join(lines)

    def send_approval_request(
        self,
        work_item_id,
        agent_name,
        message,
        approval_id=None,
        artifact_summary=None,
        artifact_links=None,
    ):
        """Write an approval request to the work item discussion."""
        comment = self.format_approval_comment(
            agent_name=agent_name,
            message=message,
            approval_id=approval_id,
            artifact_summary=artifact_summary,
            artifact_links=artifact_links,
        )
        self.ado.post_work_item_comment(work_item_id, comment)
        return True

    def work_item_id_from_text(self, *values):
        text = " ".join(str(value) for value in values if value)
        match = re.search(r"work item\s+([A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def send_notification(self, title, message, work_item_id=None):
        """Write a status or missing-information notification to work item discussion."""
        target_work_item_id = work_item_id or self.work_item_id_from_text(title, message)
        if target_work_item_id is None:
            print("Skipping DevOps discussion update because work_item_id is unknown.")
            return False

        comment = f"{title}\n\n{message}"
        self.ado.post_work_item_comment(target_work_item_id, comment)
        return True
