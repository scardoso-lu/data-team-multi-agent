"""
Approval webhook router (FastAPI).

Teams Adaptive Card action buttons POST to POST /webhook/approve.
This endpoint resolves the pending ApprovalGate record so the StateLoop
can advance the work item to the next Kanban column.

In production: replace this FastAPI router with an Azure Function
(HTTP trigger, Python v2 programming model) that writes to the same
Azure Table Storage — the ApprovalGate.resolve() call is identical.

Security note: In production add Azure AD token validation on this
endpoint (verify the Bearer token issued by Teams / Power Automate)
to prevent spoofed approval callbacks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from data_team.hitl.approval_gate import ApprovalGate
from data_team.orchestrator.config import get_settings
from data_team.orchestrator.models import ApprovalWebhookPayload

router = APIRouter(tags=["HITL Approvals"])

# The gate singleton is shared with the StateLoop via the app state.
# We retrieve it from `request.app.state.gate` set in main.py.

def _get_gate(request: Request) -> ApprovalGate:
    gate: ApprovalGate | None = getattr(request.app.state, "gate", None)
    if gate is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Approval gate not initialised",
        )
    return gate


@router.post(
    "/approve",
    summary="Receive Teams Adaptive Card approval or rejection",
    status_code=status.HTTP_200_OK,
)
async def receive_approval(
    payload: ApprovalWebhookPayload,
    gate: ApprovalGate = Depends(_get_gate),
) -> dict:
    """
    Called by the Teams Adaptive Card action buttons.

    Expected JSON body:
        {
          "work_item_id": 42,
          "action": "approve",          // or "reject"
          "resolved_by": "user@org.com",
          "reason": ""                  // required when action == "reject"
        }
    """
    if payload.action not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid action '{payload.action}'. Must be 'approve' or 'reject'.",
        )

    if payload.action == "reject" and not payload.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A rejection reason is required.",
        )

    gate.resolve(
        work_item_id=payload.work_item_id,
        action=payload.action,
        resolved_by=payload.resolved_by,
        reason=payload.reason,
    )

    return {
        "work_item_id": payload.work_item_id,
        "status": "approved" if payload.action == "approve" else "rejected",
        "resolved_by": payload.resolved_by,
    }


@router.get(
    "/status/{work_item_id}",
    summary="Check current approval status for a work item",
)
async def get_approval_status(
    work_item_id: int,
    gate: ApprovalGate = Depends(_get_gate),
) -> dict:
    record = gate._read(work_item_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No approval record found for work item {work_item_id}",
        )
    return record.model_dump(mode="json")
