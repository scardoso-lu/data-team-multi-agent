"""
Domain models shared across the orchestrator, agents, and HITL layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BoardColumn(StrEnum):
    ARCHITECTURE = "01 - Architecture"
    ENGINEERING = "02 - Engineering"
    QA = "03 - QA & Testing"
    ANALYTICS = "04 - Analytics & BI"
    GOVERNANCE = "05 - Governance & Review"
    DONE = "Done"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class WorkItem(BaseModel):
    """Normalised representation of an ADO work item."""

    id: int
    title: str
    description: str = ""
    acceptance_criteria: str = ""
    column: str
    assigned_to: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Arbitrary ADO field bag — agents can read raw fields from here
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """Lifecycle record for a single HITL approval gate."""

    work_item_id: int
    agent_name: str
    column: str
    summary: str
    artifacts: list[str] = Field(default_factory=list)
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    status: ApprovalStatus = ApprovalStatus.PENDING
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    rejection_reason: str | None = None


class AgentResult(BaseModel):
    """Return value every agent's run() method must produce."""

    work_item_id: int
    agent_name: str
    success: bool
    summary: str
    artifacts_created: list[str] = Field(default_factory=list)
    tool_calls_made: int = 0
    error: str | None = None


class ApprovalWebhookPayload(BaseModel):
    """Shape of the JSON body Teams posts to /webhook/approve."""

    work_item_id: int
    action: str          # "approve" | "reject"
    resolved_by: str     # Teams user display name
    reason: str = ""
