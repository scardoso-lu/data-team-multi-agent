# Polling approval store
# Agents create approval records and poll this store for human decisions.

import time

from approvals import APPROVED, PENDING, REJECTED, TIMED_OUT, InMemoryApprovalStore


class ApprovalServer:
    """Stores approvals and lets agents poll for decisions."""

    def __init__(self, store=None):
        self.store = store or InMemoryApprovalStore()

    def approve(self, approval_id, decided_by=None, comments=None):
        return self.decide(
            approval_id,
            APPROVED,
            decided_by=decided_by,
            comments=comments,
        )

    def create_approval(self, record):
        return self.store.create(record)

    def decide(self, approval_id, status, decided_by=None, comments=None):
        decided = self.store.decide(
            approval_id,
            status,
            decided_by=decided_by,
            comments=comments,
        )
        return decided

    def reject(self, approval_id, decided_by=None, comments=None):
        return self.decide(
            approval_id,
            REJECTED,
            decided_by=decided_by,
            comments=comments,
        )

    def wait_for_decision(self, approval_id, timeout_seconds, poll_seconds):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            record = self.store.get(approval_id)
            if record and record["status"] != PENDING:
                return record
            time.sleep(poll_seconds)

        record = self.store.get(approval_id)
        if record and record["status"] == PENDING:
            return self.decide(approval_id, TIMED_OUT)

        return {
            "approval_id": approval_id,
            "status": TIMED_OUT,
            "decided_by": None,
            "comments": None,
        }

    def wait_for_approval(self, approval_id, timeout_seconds, poll_seconds):
        """Backward-compatible approved/not-approved polling helper."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            record = self.store.get(approval_id)
            if record and record["status"] == APPROVED:
                return True
            time.sleep(poll_seconds)
        record = self.store.get(approval_id)
        return bool(record and record["status"] == APPROVED)
