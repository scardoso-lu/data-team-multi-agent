# ADO Integration Skill
# Handles interactions with Azure DevOps boards and repositories.

from azure.devops.connection import Connection
from azure.devops.v7_1.work_item_tracking.models import JsonPatchOperation, Wiql
from msrest.authentication import BasicAuthentication
import html
import os

from config import AppConfig

class ADOIntegration:
    """Handles Azure DevOps board and repository interactions."""
    
    def __init__(self, connection=None, config=None):
        self.config = config or AppConfig()
        self.ado_pat = os.getenv("ADO_PAT")
        self.assigned_to = os.getenv("ADO_ASSIGNED_TO")
        self.organization_url = os.getenv("ADO_ORGANIZATION_URL") or self.config.get(
            "ado",
            "organization_url",
            default="",
        )
        self.project_name = os.getenv("ADO_PROJECT_NAME") or self.config.get(
            "ado",
            "project_name",
            default="",
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

    def build_column_wiql(self, column_name, work_item_types=None):
        """Build a WIQL query for work items in a board column."""
        escaped_column = str(column_name).replace("'", "''")
        escaped_project = str(self.project_name).replace("'", "''")
        query = (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{escaped_project}' "
            f"AND [{self.column_field}] = '{escaped_column}' "
        )
        if work_item_types:
            escaped_types = [
                "'{}'".format(str(work_item_type).replace("'", "''"))
                for work_item_type in work_item_types
            ]
            query += f"AND [System.WorkItemType] IN ({', '.join(escaped_types)}) "
        return query + "ORDER BY [System.ChangedDate] ASC"

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

    def parent_work_item_url(self, work_item_client, parent_work_item_id):
        """Resolve the parent work item REST URL for hierarchy relations."""
        parent = work_item_client.get_work_item(
            id=parent_work_item_id,
            project=self.project_name or None,
        )
        parent_url = getattr(parent, "url", "")
        if parent_url:
            return parent_url

        if self.organization_url and self.project_name:
            return (
                f"{self.organization_url.rstrip('/')}/{self.project_name}"
                f"/_apis/wit/workItems/{parent_work_item_id}"
            )

        raise ValueError(
            "Cannot create child work item because the parent work item URL could "
            "not be resolved. Set ADO_ORGANIZATION_URL and ADO_PROJECT_NAME, or use "
            "an Azure DevOps client that returns WorkItem.url."
        )

    def build_child_work_item_patch(self, parent_work_item_id, story, target_column, parent_url):
        """Build JSON Patch operations for a linked engineering child work item."""
        description = self.format_story_html(story)
        return [
            JsonPatchOperation(
                op="add",
                path="/fields/System.Title",
                value=story["title"],
            ),
            JsonPatchOperation(
                op="add",
                path="/fields/System.Description",
                value=description,
            ),
            JsonPatchOperation(
                op="add",
                path=f"/fields/{self.column_field}",
                value=target_column,
            ),
            JsonPatchOperation(
                op="add",
                path="/relations/-",
                value={
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": parent_url,
                    "attributes": {"comment": "Created by Data Architect"},
                },
            ),
        ]

    def format_story_markdown(self, story, index=None):
        """Format one architect-generated story as Markdown."""
        heading = "Specification" if index is None else f"Specification {index}"
        lines = [
            f"## {heading}: {story.get('title', '')}",
            "",
            "### User Story",
            story.get("user_story", ""),
            "",
            "### Flow Specification",
            story.get("specification", ""),
            "",
            "### Acceptance Criteria",
        ]
        for criterion in story.get("acceptance_criteria", []):
            done = criterion.get("done", "") if isinstance(criterion, dict) else ""
            item = criterion.get("item", criterion) if isinstance(criterion, dict) else criterion
            marker = "x" if done == "X" else " "
            lines.append(f"- [{marker}] {item}")
        return "\n".join(lines).strip()

    def _paragraphs_html(self, text):
        paragraphs = []
        for paragraph in str(text or "").split("\n\n"):
            paragraph = paragraph.strip()
            if paragraph:
                paragraphs.append(
                    f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>"
                )
        return "\n".join(paragraphs)

    def _extract_mermaid_block(self, specification):
        text = str(specification or "")
        start_marker = "```mermaid"
        end_marker = "```"
        start = text.find(start_marker)
        if start == -1:
            return text, "", ""
        before = text[:start].strip()
        content_start = start + len(start_marker)
        end = text.find(end_marker, content_start)
        if end == -1:
            return before, text[content_start:].strip(), ""
        mermaid = text[content_start:end].strip()
        after = text[end + len(end_marker):].strip()
        return before, mermaid, after

    def format_story_html(self, story, index=None):
        """Format one architect-generated story as ADO rich-text HTML."""
        heading = "Specification" if index is None else f"Specification {index}"
        before_flow, mermaid, after_flow = self._extract_mermaid_block(
            story.get("specification", "")
        )
        lines = [
            f"<h2>{html.escape(heading)}: {html.escape(str(story.get('title', '')))}</h2>",
            "<h3>User Story</h3>",
            self._paragraphs_html(story.get("user_story", "")),
            "<h3>Flow Specification</h3>",
            self._paragraphs_html(before_flow),
        ]
        if mermaid:
            lines.extend(
                [
                    "<h4>Flowchart</h4>",
                    f"<pre><code>{html.escape(mermaid)}</code></pre>",
                ]
            )
        if after_flow:
            lines.append(self._paragraphs_html(after_flow))
        lines.append("<h3>Acceptance Criteria</h3>")
        lines.append("<ul>")
        for criterion in story.get("acceptance_criteria", []):
            done = criterion.get("done", "") if isinstance(criterion, dict) else ""
            item = criterion.get("item", criterion) if isinstance(criterion, dict) else criterion
            marker = "&#9745;" if done == "X" else "&#9744;"
            lines.append(f"<li>{marker} {html.escape(str(item))}</li>")
        lines.append("</ul>")
        return "\n".join(line for line in lines if line != "").strip()

    def format_specification_text(self, architecture_doc):
        """Format architect-generated specifications as Markdown for local/debug use."""
        lines = [
            "# Data Architect Implementation Specifications",
            "",
            f"**Source work item type:** {architecture_doc.get('source_work_item_type', '')}",
            "",
        ]
        for index, story in enumerate(architecture_doc.get("user_stories", []), start=1):
            lines.extend([self.format_story_markdown(story, index=index), ""])
        return "\n".join(lines).strip()

    def format_specification_html(self, architecture_doc):
        """Format architect-generated specifications as ADO rich-text HTML."""
        lines = [
            "<h1>Data Architect Implementation Specifications</h1>",
            (
                "<p><strong>Source work item type:</strong> "
                f"{html.escape(str(architecture_doc.get('source_work_item_type', '')))}</p>"
            ),
        ]
        for index, story in enumerate(architecture_doc.get("user_stories", []), start=1):
            lines.append(self.format_story_html(story, index=index))
        return "\n".join(lines).strip()

    def merge_specification_description(self, architecture_doc, existing_description=None):
        """Prepend generated specs to any existing work item description."""
        specification = self.format_specification_html(architecture_doc)
        existing = existing_description.strip() if isinstance(existing_description, str) else ""
        if not existing:
            return specification
        return (
            f"{specification}\n<hr>"
            "<h2>Previous Description</h2>"
            f"{self._paragraphs_html(existing)}"
        )

    def build_specification_patch(self, architecture_doc, existing_description=None):
        """Build a patch that writes generated specs to the current work item description."""
        return [
            JsonPatchOperation(
                op="add",
                path="/fields/System.Description",
                value=self.merge_specification_description(
                    architecture_doc,
                    existing_description,
                ),
            )
        ]

    def build_history_patch(self, message):
        """Build a patch that appends a discussion/history comment."""
        return [
            JsonPatchOperation(
                op="add",
                path="/fields/System.History",
                value=message,
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

    def get_work_items(self, column_name, work_item_types=None):
        """Get work items from a specific column."""
        if self.simulated:
            print(f"Getting work items from column: {column_name}")
            return self.config.copy_value("ado", "simulated_work_item_ids", default=[])

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        result = work_item_client.query_by_wiql(
            Wiql(query=self.build_column_wiql(column_name, work_item_types))
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

    def create_child_work_item(self, parent_work_item_id, work_item_type, story, target_column):
        """Create a linked child work item for an architect-produced story."""
        if self.simulated:
            child_id = f"{parent_work_item_id}-{len(str(story.get('title', 'story')))}"
            print(
                f"Created {work_item_type} {child_id} under work item "
                f"{parent_work_item_id}"
            )
            return child_id

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        parent_url = self.parent_work_item_url(work_item_client, parent_work_item_id)
        created = work_item_client.create_work_item(
            document=self.build_child_work_item_patch(
                parent_work_item_id,
                story,
                target_column,
                parent_url,
            ),
            project=self.project_name or None,
            type=work_item_type,
        )
        print(f"Created {work_item_type} {created.id} under work item {parent_work_item_id}")
        return created.id

    def post_work_item_specification(self, work_item_id, architecture_doc, existing_description=None):
        """Write generated architecture specifications to an existing work item description."""
        if self.simulated:
            print(f"Posted architecture specifications to work item {work_item_id}")
            return work_item_id

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_item_client.update_work_item(
            document=self.build_specification_patch(architecture_doc, existing_description),
            id=work_item_id,
            project=self.project_name or None,
        )
        print(f"Posted architecture specifications to work item {work_item_id}")
        return work_item_id

    def post_work_item_comment(self, work_item_id, message):
        """Post a status or missing-information comment to an ADO work item."""
        if self.simulated:
            print(f"Posted comment to work item {work_item_id}: {message}")
            return work_item_id

        connection = self.get_connection()
        work_item_client = connection.clients.get_work_item_tracking_client()
        work_item_client.update_work_item(
            document=self.build_history_patch(message),
            id=work_item_id,
            project=self.project_name or None,
        )
        print(f"Posted comment to work item {work_item_id}")
        return work_item_id
    
    def update_wiki(self, content, page_name):
        """Update the ADO Wiki with documentation."""
        if self.simulated:
            print(f"Updated wiki page {page_name}")
            return True

        connection = self.get_connection()
        wiki_client = connection.clients.get_wiki_client()
        wiki_client.create_or_update_page(
            parameters={"content": content},
            project=self.project_name,
            wiki_identifier=self.project_name,
            path=f"/{page_name}",
            version=None,
            version_descriptor=None,
        )
        print(f"Updated wiki page {page_name}")
        return True
