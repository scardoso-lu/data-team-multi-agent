from approvals import APPROVED, PENDING, REJECTED, TIMED_OUT, InMemoryApprovalStore


class FakeBoardClient:
    def __init__(self, columns, details=None, failures=None):
        self.columns = {column: list(items) for column, items in columns.items()}
        self.details = details or {}
        self.artifacts = {}
        self.failures = failures or {}
        self.claimed = []
        self.moves = []
        self.wiki_updates = []
        self.created_children = []
        self.posted_specifications = []

    def _maybe_fail(self, operation):
        remaining = self.failures.get(operation, 0)
        if remaining:
            self.failures[operation] = remaining - 1
            raise RuntimeError(f"Injected failure for {operation}")

    def get_work_items(self, column_name, work_item_types=None):
        self._maybe_fail("get_work_items")
        return list(self.columns.get(column_name, []))

    def claim_work_item(self, work_item_id):
        self._maybe_fail("claim_work_item")
        self.claimed.append(work_item_id)
        return work_item_id

    def get_work_item_details(self, work_item_id):
        self._maybe_fail("get_work_item_details")
        return self.artifacts.get(work_item_id, self.details.get(work_item_id, {}))

    def set_work_item_details(self, work_item_id, details):
        self.artifacts[work_item_id] = details
        return details

    def move_work_item(self, work_item_id, target_column):
        self._maybe_fail("move_work_item")
        for items in self.columns.values():
            if work_item_id in items:
                items.remove(work_item_id)
                break

        self.columns.setdefault(target_column, []).append(work_item_id)
        self.moves.append((work_item_id, target_column))
        return work_item_id

    def update_wiki(self, content, page_name):
        self._maybe_fail("update_wiki")
        self.wiki_updates.append({"page_name": page_name, "content": content})
        return True

    def create_child_work_item(self, parent_work_item_id, work_item_type, story, target_column):
        child_id = f"{parent_work_item_id}-child-{len(self.created_children) + 1}"
        self.created_children.append(
            {
                "id": child_id,
                "parent_work_item_id": parent_work_item_id,
                "work_item_type": work_item_type,
                "story": story,
                "target_column": target_column,
            }
        )
        return child_id

    def post_work_item_specification(self, work_item_id, architecture_doc, existing_description=None):
        self.posted_specifications.append(
            {
                "work_item_id": work_item_id,
                "architecture_doc": architecture_doc,
                "existing_description": existing_description,
            }
        )
        return work_item_id


class FakeNotificationClient:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.approval_requests = []
        self.notifications = []

    def _maybe_fail(self, operation):
        remaining = self.failures.get(operation, 0)
        if remaining:
            self.failures[operation] = remaining - 1
            raise RuntimeError(f"Injected failure for {operation}")

    def send_approval_request(self, work_item_id, agent_name, message, **metadata):
        self._maybe_fail("send_approval_request")
        self.approval_requests.append(
            {
                "work_item_id": work_item_id,
                "agent_name": agent_name,
                "message": message,
                **metadata,
            }
        )
        return True

    def send_notification(self, title, message, work_item_id=None):
        self._maybe_fail("send_notification")
        self.notifications.append(
            {"title": title, "message": message, "work_item_id": work_item_id}
        )
        return True


class FakeApprovalClient:
    def __init__(self, decision=APPROVED, decided_by="harness-reviewer", comments=None, store=None, approved=None):
        if approved is not None:
            decision = APPROVED if approved else TIMED_OUT
        self.decision = decision
        self.decided_by = decided_by
        self.comments = comments
        self.store = store or InMemoryApprovalStore()
        self.started = []
        self.waits = []

    def start(self, host, port):
        self.started.append({"host": host, "port": port})
        return host, port

    def create_approval(self, record):
        created = self.store.create(record)
        if self.decision in (APPROVED, REJECTED):
            return self.store.decide(
                created["approval_id"],
                self.decision,
                decided_by=self.decided_by,
                comments=self.comments,
            )
        return created

    def wait_for_decision(self, approval_id, timeout_seconds, poll_seconds):
        self.waits.append(
            {
                "approval_id": approval_id,
                "timeout_seconds": timeout_seconds,
                "poll_seconds": poll_seconds,
            }
        )
        record = self.store.get(approval_id)
        if not record:
            raise KeyError(f"Unknown approval_id: {approval_id}")
        if self.decision == TIMED_OUT and record["status"] == PENDING:
            return self.store.decide(approval_id, TIMED_OUT)
        return record

    def wait_for_approval(self, work_item_id, timeout_seconds, poll_seconds):
        self.waits.append(
            {
                "work_item_id": work_item_id,
                "timeout_seconds": timeout_seconds,
                "poll_seconds": poll_seconds,
            }
        )
        return self.decision == APPROVED


class FakeGovernanceClient:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.metadata = []

    def _maybe_fail(self, operation):
        remaining = self.failures.get(operation, 0)
        if remaining:
            self.failures[operation] = remaining - 1
            raise RuntimeError(f"Injected failure for {operation}")

    def publish_metadata(self, metadata):
        self._maybe_fail("publish_metadata")
        self.metadata.append(metadata)
        return True
