"""
ApprovalGate — Human-in-the-Loop state management.

Lifecycle of an approval:
  1. An agent completes its work and calls `request_and_wait()`.
  2. The gate sends a Teams Adaptive Card (via teams.py) and writes a
     PENDING record to Azure Table Storage.
  3. The gate polls Table Storage every `_POLL_INTERVAL_SECONDS` until
     the record transitions to APPROVED, REJECTED, or the timeout elapses.
  4. The /webhook/approve FastAPI endpoint (webhook.py) receives the Teams
     Adaptive Card callback and updates the Table Storage record.

Azure Table Storage schema:
  - PartitionKey : "approvals"
  - RowKey       : str(work_item_id)
  - status       : "pending" | "approved" | "rejected" | "timed_out"
  - resolved_by  : Teams UPN of the approver
  - resolved_at  : ISO-8601 timestamp
  - reason       : rejection reason (if rejected)

In production, swap the FastAPI webhook for an Azure Function (HTTP trigger)
that writes to the same Table Storage — the gate code remains unchanged.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from azure.data.tables import TableServiceClient
from azure.identity import ClientSecretCredential

from data_team.orchestrator.config import Settings
from data_team.orchestrator.models import ApprovalRequest, ApprovalStatus
from data_team.tools.teams import teams_send_approval_card

log = structlog.get_logger()

_TABLE_NAME = "agentapprovals"
_POLL_INTERVAL_SECONDS = 15


class ApprovalGate:
    """
    Thread-safe approval gate backed by Azure Table Storage.
    Works with any number of concurrent StateLoop tasks.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._table = self._make_table_client(settings)
        self._ensure_table()

    # ── Public interface ──────────────────────────────────────────────────────

    async def request_and_wait(
        self,
        work_item_id: int,
        agent_name: str,
        column: str,
        summary: str,
        artifacts: list[str] | None = None,
    ) -> ApprovalRequest:
        """
        Send the approval card to Teams, persist the request, and block until
        a human approves/rejects or the timeout elapses.
        """
        req = ApprovalRequest(
            work_item_id=work_item_id,
            agent_name=agent_name,
            column=column,
            summary=summary,
            artifacts=artifacts or [],
        )

        self._write_pending(req)
        log.info("approval.requested", work_item_id=work_item_id, agent=agent_name)

        # Post Adaptive Card to Teams (non-blocking — fire and forget the card)
        try:
            teams_send_approval_card(
                self.settings,
                work_item_id=work_item_id,
                agent_name=agent_name,
                column=column,
                summary=summary,
                artifacts=artifacts or [],
            )
        except Exception:
            log.exception("approval.teams_card_failed", work_item_id=work_item_id)

        # Poll until resolved or timed out
        timeout_seconds = self.settings.approval_timeout_hours * 3600
        elapsed = 0.0

        while elapsed < timeout_seconds:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            current = self._read(work_item_id)
            if current and current.status != ApprovalStatus.PENDING:
                log.info(
                    "approval.resolved",
                    work_item_id=work_item_id,
                    status=current.status,
                    resolved_by=current.resolved_by,
                )
                return current

        # Timeout — mark and return
        timed_out = req.model_copy(
            update={
                "status": ApprovalStatus.TIMED_OUT,
                "resolved_at": datetime.now(timezone.utc),
            }
        )
        self._update_status(
            work_item_id,
            ApprovalStatus.TIMED_OUT,
            resolved_by="system",
            reason="Approval timed out",
        )
        log.warning("approval.timed_out", work_item_id=work_item_id)
        return timed_out

    def resolve(
        self,
        work_item_id: int,
        action: str,
        resolved_by: str,
        reason: str = "",
    ) -> None:
        """
        Called by the webhook when a human clicks Approve or Reject.
        `action` must be "approve" or "reject".
        """
        status = (
            ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
        )
        self._update_status(work_item_id, status, resolved_by=resolved_by, reason=reason)
        log.info(
            "approval.resolved_via_webhook",
            work_item_id=work_item_id,
            status=status,
            resolved_by=resolved_by,
        )

    # ── Azure Table Storage helpers ───────────────────────────────────────────

    @staticmethod
    def _make_table_client(settings: Settings):
        cred = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )
        # Derive the storage account URL from the tenant/project convention.
        # Override APPROVAL_STORAGE_URL in .env if you use a dedicated account.
        storage_url = getattr(settings, "approval_storage_url", None)
        if not storage_url:
            # Fallback: use the PAT-based connection string pattern common in ADO setups.
            # In real deployments set APPROVAL_STORAGE_URL explicitly.
            raise EnvironmentError(
                "APPROVAL_STORAGE_URL must be set in .env "
                "(e.g. https://<account>.table.core.windows.net)"
            )
        svc = TableServiceClient(endpoint=storage_url, credential=cred)
        return svc.get_table_client(_TABLE_NAME)

    def _ensure_table(self) -> None:
        try:
            self._table.create_table()
        except Exception:
            pass  # Table already exists

    def _write_pending(self, req: ApprovalRequest) -> None:
        entity = {
            "PartitionKey": "approvals",
            "RowKey": str(req.work_item_id),
            "status": ApprovalStatus.PENDING,
            "agent_name": req.agent_name,
            "column": req.column,
            "summary": req.summary[:32000],  # Table Storage cell limit
            "artifacts": ",".join(req.artifacts),
            "requested_at": req.requested_at.isoformat(),
            "resolved_by": "",
            "resolved_at": "",
            "reason": "",
        }
        self._table.upsert_entity(entity)

    def _read(self, work_item_id: int) -> ApprovalRequest | None:
        try:
            e = self._table.get_entity("approvals", str(work_item_id))
        except Exception:
            return None

        resolved_at = None
        if e.get("resolved_at"):
            try:
                resolved_at = datetime.fromisoformat(e["resolved_at"])
            except ValueError:
                pass

        return ApprovalRequest(
            work_item_id=work_item_id,
            agent_name=e.get("agent_name", ""),
            column=e.get("column", ""),
            summary=e.get("summary", ""),
            artifacts=e.get("artifacts", "").split(",") if e.get("artifacts") else [],
            status=ApprovalStatus(e.get("status", "pending")),
            resolved_by=e.get("resolved_by") or None,
            resolved_at=resolved_at,
            rejection_reason=e.get("reason") or None,
        )

    def _update_status(
        self,
        work_item_id: int,
        status: ApprovalStatus,
        resolved_by: str,
        reason: str = "",
    ) -> None:
        patch = {
            "PartitionKey": "approvals",
            "RowKey": str(work_item_id),
            "status": status,
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        self._table.update_entity(patch, mode="merge")
