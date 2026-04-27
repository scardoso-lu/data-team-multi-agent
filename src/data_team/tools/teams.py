"""
Microsoft Teams tools — message delivery and HITL approval cards via Graph API.

Authentication uses the ClientSecretCredential from azure-identity; the app
registration must have the following Graph application permissions:
  - ChannelMessage.Send
  - Chat.ReadWrite (for bot replies if needed)

Adaptive Card approval flow:
  1. Agent calls `teams_send_approval_card`.
  2. Card is posted to the designated channel with Approve / Reject buttons.
  3. Each button triggers an HTTP POST to `settings.approval_webhook_url`
     (the /webhook/approve FastAPI endpoint, or an Azure Function in production).
  4. The ApprovalGate polls Azure Table Storage until the status resolves.
"""

from __future__ import annotations

from typing import Any

import httpx
from azure.identity import ClientSecretCredential

from data_team.orchestrator.config import Settings

# ── Anthropic Tool Schemas ─────────────────────────────────────────────────────

TEAMS_TOOLS: list[dict[str, Any]] = [
    {
        "name": "teams_send_message",
        "description": (
            "Post a plain-text or Markdown message to the configured Teams channel. "
            "Use for status updates, progress notifications, and summaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message body. Supports basic HTML/Markdown.",
                },
                "subject": {
                    "type": "string",
                    "description": "Optional subject line shown in the Teams message header.",
                    "default": "",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "teams_send_approval_card",
        "description": (
            "Post an Adaptive Card approval request to the configured Teams channel. "
            "The card displays the agent's work summary and two action buttons: "
            "Approve and Reject. Each button calls back to the approval webhook. "
            "Call this AFTER completing all work on a work item and BEFORE "
            "reporting the task as finished — the ApprovalGate will block "
            "until a human responds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_item_id": {
                    "type": "integer",
                    "description": "ADO work item ID this approval is for.",
                },
                "agent_name": {
                    "type": "string",
                    "description": "Display name of the agent requesting approval.",
                },
                "column": {
                    "type": "string",
                    "description": "Current Kanban column, e.g. '02 - Engineering'.",
                },
                "summary": {
                    "type": "string",
                    "description": "Plain-text summary of everything the agent did.",
                },
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of artifact names/URLs produced (wiki pages, branches, etc.).",
                },
            },
            "required": ["work_item_id", "agent_name", "column", "summary"],
        },
    },
    {
        "name": "teams_send_final_summary",
        "description": (
            "Post a rich end-of-lifecycle summary card to Teams. "
            "Called exclusively by the Data Steward agent as the final step "
            "before closing a work item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_item_id": {"type": "integer"},
                "work_item_title": {"type": "string"},
                "lifecycle_summary": {
                    "type": "string",
                    "description": "Markdown narrative covering all five pipeline stages.",
                },
                "purview_asset_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Direct Purview catalog links to registered assets.",
                },
                "power_bi_report_url": {
                    "type": "string",
                    "description": "URL of the published Power BI report (if any).",
                    "default": "",
                },
            },
            "required": ["work_item_id", "work_item_title", "lifecycle_summary"],
        },
    },
]

# ── Graph API helpers ──────────────────────────────────────────────────────────

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"


def _bearer_token(settings: Settings) -> str:
    cred = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    token = cred.get_token(_GRAPH_SCOPE)
    return token.token


def _channel_message_url(settings: Settings) -> str:
    return (
        f"{_GRAPH_BASE}/teams/{settings.teams_team_id}"
        f"/channels/{settings.teams_channel_id}/messages"
    )


# ── Adaptive Card builder ──────────────────────────────────────────────────────


def _build_approval_card(
    settings: Settings,
    work_item_id: int,
    agent_name: str,
    column: str,
    summary: str,
    artifacts: list[str],
) -> dict:
    """
    Returns an Adaptive Card (v1.4) payload suitable for a Teams channel message.
    The Approve / Reject actions POST JSON to the approval webhook URL so the
    ApprovalGate can resolve the pending request.
    """
    artifact_facts = [{"title": "Artifact", "value": a} for a in artifacts] if artifacts else []

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"⏳ Approval Required — WI #{work_item_id}",
                            "weight": "Bolder",
                            "size": "Large",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Agent", "value": agent_name},
                                {"title": "Stage", "value": column},
                                {"title": "Work Item", "value": str(work_item_id)},
                            ]
                            + artifact_facts,
                        },
                        {
                            "type": "TextBlock",
                            "text": "**Summary of work completed:**",
                            "wrap": True,
                        },
                        {"type": "TextBlock", "text": summary, "wrap": True},
                    ],
                    "actions": [
                        {
                            "type": "Action.Http",
                            "title": "✅ Approve",
                            "method": "POST",
                            "url": settings.approval_webhook_url,
                            "headers": [{"name": "Content-Type", "value": "application/json"}],
                            "body": (
                                f'{{"work_item_id":{work_item_id},'
                                f'"action":"approve",'
                                f'"resolved_by":"{{{{MSTeams.userPrincipalName}}}}",'
                                f'"reason":""}}'
                            ),
                        },
                        {
                            "type": "Action.ShowCard",
                            "title": "❌ Reject",
                            "card": {
                                "type": "AdaptiveCard",
                                "body": [
                                    {
                                        "type": "Input.Text",
                                        "id": "rejection_reason",
                                        "placeholder": "Reason for rejection (required)",
                                        "isMultiline": True,
                                    }
                                ],
                                "actions": [
                                    {
                                        "type": "Action.Http",
                                        "title": "Submit Rejection",
                                        "method": "POST",
                                        "url": settings.approval_webhook_url,
                                        "headers": [
                                            {"name": "Content-Type", "value": "application/json"}
                                        ],
                                        "body": (
                                            f'{{"work_item_id":{work_item_id},'
                                            f'"action":"reject",'
                                            f'"resolved_by":"{{{{MSTeams.userPrincipalName}}}}",'
                                            f'"reason":"{{{{rejection_reason.value}}}}" }}'
                                        ),
                                    }
                                ],
                            },
                        },
                    ],
                },
            }
        ],
    }


# ── Tool implementations ───────────────────────────────────────────────────────


def teams_send_message(settings: Settings, message: str, subject: str = "") -> dict:
    token = _bearer_token(settings)
    payload: dict[str, Any] = {
        "body": {"contentType": "html", "content": message},
    }
    if subject:
        payload["subject"] = subject

    with httpx.Client() as client:
        r = client.post(
            _channel_message_url(settings),
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
    return {"message_id": r.json().get("id"), "status": "sent"}


def teams_send_approval_card(
    settings: Settings,
    work_item_id: int,
    agent_name: str,
    column: str,
    summary: str,
    artifacts: list[str] | None = None,
) -> dict:
    card = _build_approval_card(
        settings, work_item_id, agent_name, column, summary, artifacts or []
    )
    token = _bearer_token(settings)
    with httpx.Client() as client:
        r = client.post(
            _channel_message_url(settings),
            json=card,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
    return {"message_id": r.json().get("id"), "approval_status": "pending"}


def teams_send_final_summary(
    settings: Settings,
    work_item_id: int,
    work_item_title: str,
    lifecycle_summary: str,
    purview_asset_urls: list[str] | None = None,
    power_bi_report_url: str = "",
) -> dict:
    assets_html = "".join(
        f"<li><a href='{u}'>{u}</a></li>" for u in (purview_asset_urls or [])
    )
    pbi_line = (
        f"<p><strong>Power BI Report:</strong> <a href='{power_bi_report_url}'>Open Report</a></p>"
        if power_bi_report_url
        else ""
    )
    body = (
        f"<h2>✅ WI #{work_item_id} — {work_item_title} — Pipeline Complete</h2>"
        f"<p>{lifecycle_summary}</p>"
        f"<ul>{assets_html}</ul>"
        f"{pbi_line}"
    )
    return teams_send_message(settings, body, subject=f"WI #{work_item_id} Closed")


# ── Unified dispatcher ────────────────────────────────────────────────────────


async def execute_teams_tool(settings: Settings, tool_name: str, tool_input: dict) -> Any:
    dispatch = {
        "teams_send_message":       lambda: teams_send_message(settings, **tool_input),
        "teams_send_approval_card": lambda: teams_send_approval_card(settings, **tool_input),
        "teams_send_final_summary": lambda: teams_send_final_summary(settings, **tool_input),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown Teams tool: {tool_name}")
    return fn()
