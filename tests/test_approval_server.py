import os
import sys
import threading
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from approval_server import ApprovalServer


def test_approval_server_records_posted_approval():
    approvals = ApprovalServer()

    approvals.approve("12345")

    assert approvals.is_approved("12345")
    assert approvals.wait_for_approval(
        "12345",
        timeout_seconds=0.1,
        poll_seconds=0.01
    )


def test_approval_server_waits_for_later_approval():
    approvals = ApprovalServer()

    def approve_later():
        time.sleep(0.01)
        approvals.approve("67890")

    thread = threading.Thread(target=approve_later)
    thread.start()

    assert approvals.wait_for_approval(
        "67890",
        timeout_seconds=1,
        poll_seconds=0.01
    )
    thread.join()


if __name__ == "__main__":
    test_approval_server_records_posted_approval()
    test_approval_server_waits_for_later_approval()
