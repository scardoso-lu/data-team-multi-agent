from typing import Protocol


class BoardClient(Protocol):
    def get_work_items(self, column_name, work_item_types=None):
        ...

    def claim_work_item(self, work_item_id):
        ...

    def get_work_item_details(self, work_item_id):
        ...

    def move_work_item(self, work_item_id, target_column):
        ...

    def create_child_work_item(self, parent_work_item_id, work_item_type, story, target_column):
        ...

    def post_work_item_specification(self, work_item_id, architecture_doc, existing_description=None):
        ...

    def update_wiki(self, content, page_name):
        ...


class NotificationClient(Protocol):
    def send_approval_request(
        self,
        work_item_id,
        agent_name,
        message,
        approval_id=None,
        artifact_summary=None,
        artifact_links=None,
    ):
        ...

    def send_notification(self, title, message, work_item_id=None):
        ...


class FabricClient(Protocol):
    def create_workspace(self, workspace_name):
        ...

    def deploy_pipeline(self, pipeline_name, workspace_name):
        ...


class GovernanceClient(Protocol):
    def publish_metadata(self, metadata):
        ...


class ApprovalClient(Protocol):
    def create_approval(self, record):
        ...

    def wait_for_decision(self, approval_id, timeout_seconds, poll_seconds):
        ...

    def wait_for_approval(self, work_item_id, timeout_seconds, poll_seconds):
        ...
