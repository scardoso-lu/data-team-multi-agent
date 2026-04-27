"""
Azure DevOps tools: Boards (work items), Git (commits / PRs), Wiki pages.

Each public constant named *_TOOLS is a list[dict] of Anthropic tool schemas
ready to pass to `client.messages.create(tools=...)`.

Alongside each schema block is the Python implementation that the agent's
tool-dispatch layer calls when Claude emits a `tool_use` content block.
"""

from __future__ import annotations

from typing import Any

from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication

from data_team.orchestrator.config import Settings
from data_team.orchestrator.models import WorkItem

# ── Anthropic Tool Schemas ─────────────────────────────────────────────────────

ADO_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ado_get_work_item",
        "description": (
            "Fetch full details of an Azure DevOps work item by ID, "
            "including title, description, acceptance criteria, and all custom fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_item_id": {
                    "type": "integer",
                    "description": "Numeric ADO work item ID.",
                },
            },
            "required": ["work_item_id"],
        },
    },
    {
        "name": "ado_update_work_item",
        "description": (
            "Patch one or more fields on an Azure DevOps work item. "
            "Use ADO field reference names as keys "
            "(e.g. 'System.Description', 'Microsoft.VSTS.Common.AcceptanceCriteria')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_item_id": {"type": "integer"},
                "fields": {
                    "type": "object",
                    "description": "Map of ADO field reference names → new values.",
                    "additionalProperties": True,
                },
            },
            "required": ["work_item_id", "fields"],
        },
    },
    {
        "name": "ado_create_wiki_page",
        "description": (
            "Create or update a page in the Azure DevOps project Wiki. "
            "Content must be valid Markdown. "
            "The path is relative to the wiki root, e.g. '/architecture/customer-360-model'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Wiki page path, e.g. '/architecture/data-model'.",
                },
                "content": {
                    "type": "string",
                    "description": "Full Markdown content for the page.",
                },
                "comment": {
                    "type": "string",
                    "description": "Commit comment surfaced in the wiki history.",
                    "default": "Updated by Data Team Agent",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "ado_commit_files",
        "description": (
            "Commit one or more files to the Azure DevOps Git repository. "
            "Supports adding new files or editing existing ones. "
            "Creates the branch if it does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Target branch name, e.g. 'feature/wi-42-bronze-pipeline'.",
                },
                "commit_message": {"type": "string"},
                "files": {
                    "type": "array",
                    "description": "List of file operations to include in the commit.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Repo-relative file path, e.g. 'src/pipelines/bronze_ingest.py'.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Full UTF-8 file content.",
                            },
                            "change_type": {
                                "type": "string",
                                "enum": ["add", "edit", "delete"],
                                "default": "add",
                            },
                        },
                        "required": ["path", "content"],
                    },
                    "minItems": 1,
                },
            },
            "required": ["branch", "commit_message", "files"],
        },
    },
    {
        "name": "ado_create_pull_request",
        "description": (
            "Open a pull request in the Azure DevOps Git repository "
            "and optionally link it to one or more work items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_branch": {
                    "type": "string",
                    "description": "Branch containing the new commits.",
                },
                "target_branch": {
                    "type": "string",
                    "default": "main",
                    "description": "Branch to merge into.",
                },
                "title": {"type": "string"},
                "description": {
                    "type": "string",
                    "description": "Markdown PR body.",
                },
                "work_item_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "ADO work item IDs to link to the PR.",
                },
                "auto_complete": {
                    "type": "boolean",
                    "default": False,
                    "description": "Merge automatically when all policies pass.",
                },
            },
            "required": ["source_branch", "title"],
        },
    },
    {
        "name": "ado_get_wiki_page",
        "description": "Read the current content of a wiki page by path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Wiki page path."},
            },
            "required": ["path"],
        },
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────────


def _conn(settings: Settings) -> Connection:
    creds = BasicAuthentication("", settings.ado_pat)
    return Connection(base_url=settings.ado_org_url, creds=creds)


def _wit(settings: Settings):
    return _conn(settings).clients.get_work_item_tracking_client()


def _git(settings: Settings):
    return _conn(settings).clients.get_git_client()


def _wiki(settings: Settings):
    return _conn(settings).clients.get_wiki_client()


# ── Board-level helpers (used by StateLoop directly) ──────────────────────────


async def list_work_items_in_column(settings: Settings, column: str) -> list[WorkItem]:
    """WIQL query for unclaimed items sitting in a specific board column."""
    client = _wit(settings)
    wiql = {
        "query": (
            "SELECT [System.Id],[System.Title],[System.Description],"
            "[System.BoardColumn],[System.AssignedTo],"
            "[Microsoft.VSTS.Common.AcceptanceCriteria] "
            f"FROM WorkItems "
            f"WHERE [System.TeamProject] = '{settings.ado_project}' "
            f"  AND [System.BoardColumn] = '{column}' "
            f"  AND [System.State] <> 'Done'"
        )
    }
    result = client.query_by_wiql(wiql)
    if not result.work_items:
        return []

    ids = [wi.id for wi in result.work_items]
    details = client.get_work_items(ids=ids, expand="All")

    items = []
    for wi in details:
        f = wi.fields
        assigned = f.get("System.AssignedTo")
        items.append(
            WorkItem(
                id=wi.id,
                title=f.get("System.Title", ""),
                description=f.get("System.Description", ""),
                acceptance_criteria=f.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""),
                column=f.get("System.BoardColumn", ""),
                assigned_to=(
                    assigned.get("displayName") if isinstance(assigned, dict) else assigned
                ),
                raw_fields=dict(f),
            )
        )
    return items


async def claim_work_item(settings: Settings, work_item_id: int, agent_name: str) -> None:
    patch = [{"op": "add", "path": "/fields/System.AssignedTo", "value": agent_name}]
    _wit(settings).update_work_item(patch, work_item_id)


async def move_work_item(settings: Settings, work_item_id: int, target_column: str) -> None:
    patch = [
        {"op": "add", "path": "/fields/System.BoardColumn", "value": target_column},
        {"op": "add", "path": "/fields/System.AssignedTo", "value": ""},
    ]
    _wit(settings).update_work_item(patch, work_item_id)


# ── Tool implementations (called by agent dispatcher) ─────────────────────────


def ado_get_work_item(settings: Settings, work_item_id: int) -> dict:
    wi = _wit(settings).get_work_item(work_item_id, expand="All")
    return {"id": wi.id, "fields": dict(wi.fields)}


def ado_update_work_item(settings: Settings, work_item_id: int, fields: dict) -> dict:
    patch = [{"op": "add", "path": f"/fields/{k}", "value": v} for k, v in fields.items()]
    wi = _wit(settings).update_work_item(patch, work_item_id)
    return {"id": wi.id, "updated_fields": list(fields.keys())}


def ado_create_wiki_page(
    settings: Settings, path: str, content: str, comment: str = "Updated by Data Team Agent"
) -> dict:
    from azure.devops.v7_1.wiki.models import WikiPageCreateOrUpdateParameters

    params = WikiPageCreateOrUpdateParameters(content=content)
    result = _wiki(settings).create_or_update_page(
        parameters=params,
        project=settings.ado_project,
        wiki_identifier=settings.ado_wiki_id,
        path=path,
        comment=comment,
        version=None,  # None = create; pass ETag for updates
    )
    return {"path": result.page.path, "remote_url": result.page.remote_url}


def ado_get_wiki_page(settings: Settings, path: str) -> dict:
    page = _wiki(settings).get_page(
        project=settings.ado_project,
        wiki_identifier=settings.ado_wiki_id,
        path=path,
        include_content=True,
    )
    return {"path": page.page.path, "content": page.page.content or ""}


def ado_commit_files(
    settings: Settings,
    branch: str,
    commit_message: str,
    files: list[dict],
) -> dict:
    """Push one or more file changes to the ADO Git repo as a single commit."""
    from azure.devops.v7_1.git.models import (
        GitCommit,
        GitPush,
        GitRefUpdate,
        ItemContent,
        ItemContentType,
        GitChange,
    )

    git = _git(settings)

    # Resolve current branch tip (create branch off main if it doesn't exist)
    refs = git.get_refs(
        repository_id=settings.ado_repo_name,
        project=settings.ado_project,
        filter=f"heads/{branch}",
    )
    if refs:
        old_object_id = refs[0].object_id
    else:
        main_refs = git.get_refs(
            repository_id=settings.ado_repo_name,
            project=settings.ado_project,
            filter="heads/main",
        )
        old_object_id = main_refs[0].object_id if main_refs else "0" * 40

    changes = [
        GitChange(
            change_type=f.get("change_type", "add"),
            item={"path": f["path"]},
            new_content=ItemContent(
                content=f["content"],
                content_type=ItemContentType.raw_text,
            ),
        )
        for f in files
    ]

    push = GitPush(
        ref_updates=[GitRefUpdate(name=f"refs/heads/{branch}", old_object_id=old_object_id)],
        commits=[GitCommit(comment=commit_message, changes=changes)],
    )
    result = git.create_push(push, repository_id=settings.ado_repo_name, project=settings.ado_project)
    return {"push_id": result.push_id, "branch": branch, "files_committed": len(files)}


def ado_create_pull_request(
    settings: Settings,
    source_branch: str,
    title: str,
    target_branch: str = "main",
    description: str = "",
    work_item_ids: list[int] | None = None,
    auto_complete: bool = False,
) -> dict:
    from azure.devops.v7_1.git.models import GitPullRequest, ResourceRef

    git = _git(settings)
    pr = GitPullRequest(
        title=title,
        description=description,
        source_ref_name=f"refs/heads/{source_branch}",
        target_ref_name=f"refs/heads/{target_branch}",
        work_item_refs=[ResourceRef(id=str(wid)) for wid in (work_item_ids or [])],
    )
    result = git.create_pull_request(pr, repository_id=settings.ado_repo_name, project=settings.ado_project)
    return {"pull_request_id": result.pull_request_id, "url": result.url}


# ── Unified dispatcher ────────────────────────────────────────────────────────


async def execute_ado_tool(settings: Settings, tool_name: str, tool_input: dict) -> Any:
    dispatch = {
        "ado_get_work_item":    lambda: ado_get_work_item(settings, **tool_input),
        "ado_update_work_item": lambda: ado_update_work_item(settings, **tool_input),
        "ado_create_wiki_page": lambda: ado_create_wiki_page(settings, **tool_input),
        "ado_get_wiki_page":    lambda: ado_get_wiki_page(settings, **tool_input),
        "ado_commit_files":     lambda: ado_commit_files(settings, **tool_input),
        "ado_create_pull_request": lambda: ado_create_pull_request(settings, **tool_input),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown ADO tool: {tool_name}")
    return fn()
