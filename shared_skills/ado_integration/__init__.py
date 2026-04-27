# ADO Integration Skill
# Handles interactions with Azure DevOps boards and repositories.

from azure.devops.connection import Connection
from azure.devops.v7_1.work_item_tracking.models import JsonPatchOperation, Wiql
from msrest.authentication import BasicAuthentication
import os

from config import AppConfig

class ADOIntegration:
    """Handles Azure DevOps board and repository interactions."""
    
    def __init__(self, connection=None, config=None):
        self.config = config or AppConfig()
        self.ado_pat = self.config.from_env("ado", "pat_env")
        self.assigned_to = self.config.from_env("ado", "assigned_to_env")
        self.organization_url = os.getenv(
            "ADO_ORGANIZATION_URL",
            self.config.require("ado", "organization_url")
        )
        self.project_name = os.getenv(
            "ADO_PROJECT_NAME",
            self.config.require("ado", "project_name")
        )
        self.column_field = self.config.require("ado", "column_field")
        self.claimed_tag = self.config.require("ado", "claimed_tag")
        self._connection = connection

    @property
    def simulated(self):
        return not self.ado_pat and self._connection is None
        
    def get_connection(self):
        """Establish a connection to Azure DevOps."""
        if self._connection:
            return self._connection
        credentials = BasicAuthentication("", self.ado_pat)
        return Connection(base_url=self.organization_url, creds=credentials)

    def build_column_wiql(self, column_name):
        """Build a WIQL query for work items in a board column."""
        escaped_column = str(column_name).replace("'", "''")
        escaped_project = str(self.project_name).replace("'", "''")
        return (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{escaped_project}' "
            f"AND [{self.column_field}] = '{escaped_column}' "
            "ORDER BY [System.ChangedDate] ASC"
        )

    def build_claim_patch(self):
        """Build JSON Patch operations for claiming a work item."""
        if self.assigned_to:
            return [
                JsonPatchOperation(
                    op="add",
                    path="/fields/System.AssignedTo",
                    value=self.assigned_to,
                )
            ]

        return [
            JsonPatchOperation(
                op="add",
                path="/fields/System.Tags",
                value=self.claimed_tag,
            )
        ]

    def build_move_patch(self, target_column):
        """Build JSON Patch operations for moving a work item."""
        return [
            JsonPatchOperation(
                op="add",
                path=f"/fields/{self.column_field}",
                value=target_column,
            )
        ]
    
    def claim_work_item(self, work_item_id):
        """Claim a work item for the current agent."""
        if self.simulated:
            print(f"Claimed work item {work_item_id}")
            return work_item_id

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_item_client.update_work_item(
            document=self.build_claim_patch(),
            id=work_item_id,
            project=self.project_name,
        )
        print(f"Claimed work item {work_item_id}")
        return work_item_id

    def get_work_items(self, column_name):
        """Get work items from a specific column."""
        if self.simulated:
            print(f"Getting work items from column: {column_name}")
            return self.config.copy_value("ado", "simulated_work_item_ids", default=[])

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        result = work_item_client.query_by_wiql(
            Wiql(query=self.build_column_wiql(column_name)),
            project=self.project_name,
        )
        print(f"Getting work items from column: {column_name}")
        return [item.id for item in getattr(result, "work_items", [])]

    def get_work_item_details(self, work_item_id):
        """Get details of a specific work item."""
        if self.simulated:
            print(f"Getting details for work item: {work_item_id}")
            return self.config.copy_value("ado", "simulated_work_item_details", default={})

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_item = work_item_client.get_work_item(
            id=work_item_id,
            project=self.project_name,
            expand="All",
        )
        print(f"Getting details for work item: {work_item_id}")
        return getattr(work_item, "fields", {})
    
    def move_work_item(self, work_item_id, target_column):
        """Move a work item to the next column."""
        if self.simulated:
            print(f"Moved work item {work_item_id} to {target_column}")
            return work_item_id

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_item_client.update_work_item(
            document=self.build_move_patch(target_column),
            id=work_item_id,
            project=self.project_name,
        )
        print(f"Moved work item {work_item_id} to {target_column}")
        return work_item_id
    
    def update_wiki(self, content, page_name):
        """Update the ADO Wiki with documentation."""
        if self.simulated:
            print(f"Updated wiki page {page_name}")
            return True

        connection = self.get_connection()
        wiki_client = connection.clients.get_wiki_client()
        wiki_client.create_or_update_page(
            project=self.project_name,
            wiki_identifier=self.project_name,
            path=f"/{page_name}",
            parameters={"content": content},
            version_descriptor=None,
        )
        print(f"Updated wiki page {page_name}")
        return True
