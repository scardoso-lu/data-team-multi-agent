from typing import Protocol


class BoardClient(Protocol):
    def get_work_items(self, column_name):
        ...

    def claim_work_item(self, work_item_id):
        ...

    def get_work_item_details(self, work_item_id):
        ...

    def move_work_item(self, work_item_id, target_column):
        ...

    def update_wiki(self, content, page_name):
        ...


class NotificationClient(Protocol):
    def send_approval_request(self, work_item_id, agent_name, message, callback_url):
        ...

    def send_notification(self, title, message):
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
    def wait_for_approval(self, work_item_id, timeout_seconds, poll_seconds):
        ...

    def start(self, host, port):
        ...
