import time

from events import AGENT_FAILED


class WorkItemBlocked(Exception):
    """Raised when a work item needs human input before it can continue."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
        self.message = message


def retry_operation(operation, max_retries, retry_delay_seconds):
    """Run an operation with simple retry semantics."""
    attempts = 0
    while True:
        try:
            return operation()
        except WorkItemBlocked:
            raise
        except Exception:
            attempts += 1
            if attempts > max_retries:
                raise
            if retry_delay_seconds:
                time.sleep(retry_delay_seconds)


def failure_result(agent_name, work_item_id, exc, events=None, ado=None, error_column=None):
    """Emit failure and optionally move the item to an error column."""
    if events:
        events.emit(AGENT_FAILED, agent_name, work_item_id, error=str(exc))

    moved_to = None
    if ado and error_column and work_item_id is not None:
        try:
            ado.move_work_item(work_item_id, error_column)
            moved_to = error_column
        except Exception:
            moved_to = None

    return {
        "agent": agent_name,
        "status": "failed",
        "work_item_id": work_item_id,
        "error": str(exc),
        "moved_to": moved_to,
    }
