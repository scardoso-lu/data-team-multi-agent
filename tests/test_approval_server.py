import threading
import time

from approval_server import ApprovalServer
from approvals import (
    APPROVED,
    PENDING,
    REJECTED,
    TIMED_OUT,
    JsonFileApprovalStore,
    new_approval_record,
)


def test_approval_server_records_approval_decision():
    approvals = ApprovalServer()
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    approvals.approve(created["approval_id"])

    assert approvals.wait_for_approval(
        created["approval_id"],
        timeout_seconds=0.1,
        poll_seconds=0.01
    )


def test_approval_server_waits_for_later_approval():
    approvals = ApprovalServer()
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    def approve_later():
        time.sleep(0.01)
        approvals.approve(created["approval_id"])

    thread = threading.Thread(target=approve_later)
    thread.start()

    assert approvals.wait_for_approval(
        created["approval_id"],
        timeout_seconds=1,
        poll_seconds=0.01
    )
    thread.join()


def test_approval_server_creates_pending_records_and_waits_for_decision():
    approvals = ApprovalServer()
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    assert created["status"] == PENDING

    def approve_later():
        time.sleep(0.01)
        approvals.decide(
            created["approval_id"],
            APPROVED,
            decided_by="reviewer@example.com",
            comments="Looks good",
        )

    thread = threading.Thread(target=approve_later)
    thread.start()

    decision = approvals.wait_for_decision(
        created["approval_id"],
        timeout_seconds=1,
        poll_seconds=0.01,
    )

    assert decision["status"] == APPROVED
    assert decision["decided_by"] == "reviewer@example.com"
    assert decision["comments"] == "Looks good"
    thread.join()


def test_approval_server_rejects_with_comments():
    approvals = ApprovalServer()
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    decision = approvals.reject(
        created["approval_id"],
        decided_by="reviewer@example.com",
        comments="Needs changes",
    )

    assert decision["status"] == REJECTED
    assert decision["decided_by"] == "reviewer@example.com"
    assert decision["comments"] == "Needs changes"


def test_approval_server_marks_pending_decisions_timed_out():
    approvals = ApprovalServer()
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    decision = approvals.wait_for_decision(
        created["approval_id"],
        timeout_seconds=0.01,
        poll_seconds=0.01,
    )

    assert decision["status"] == TIMED_OUT
    assert approvals.store.get(created["approval_id"])["status"] == TIMED_OUT


def test_approval_server_polls_json_store_for_external_decision(tmp_path):
    store = JsonFileApprovalStore(tmp_path / "approvals.json")
    approvals = ApprovalServer(store=store)
    created = approvals.create_approval(new_approval_record("1", "Data Architect", "Architecture"))

    external_store = JsonFileApprovalStore(tmp_path / "approvals.json")

    def reject_later():
        time.sleep(0.01)
        external_store.decide(
            created["approval_id"],
            REJECTED,
            decided_by="reviewer@example.com",
            comments="Revise this",
        )

    thread = threading.Thread(target=reject_later)
    thread.start()

    decision = approvals.wait_for_decision(
        created["approval_id"],
        timeout_seconds=1,
        poll_seconds=0.01,
    )
    thread.join()

    assert decision["status"] == REJECTED
    assert decision["decided_by"] == "reviewer@example.com"
    assert decision["comments"] == "Revise this"
