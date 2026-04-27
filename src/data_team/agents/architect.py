"""
Data Architect Agent — Column: 01 - Architecture

Responsibilities:
  • Read and deeply understand the business requirements in the work item.
  • Design a Medallion data model (Bronze / Silver / Gold) appropriate for
    the use case, including entity definitions, key relationships, and
    schema sketches.
  • Commit initial repository scaffolding (folder structure, README, schema
    files) to a feature branch in the ADO Git repo.
  • Publish the architecture design document to the ADO Wiki under
    /architecture/<work-item-id>-<slug>.
  • Update the work item with a brief summary and links to the wiki page
    and the feature branch.
"""

from __future__ import annotations

from typing import Any

from data_team.agents.base import BaseAgent
from data_team.tools.ado import ADO_TOOLS, execute_ado_tool
from data_team.tools.teams import TEAMS_TOOLS, execute_teams_tool

_SYSTEM_PROMPT = """\
You are the Data Architect for a Microsoft Fabric data engineering team.
Your column on the Kanban board is "01 - Architecture".

When you receive a work item your job is to:
1. Carefully read the title, description, and acceptance criteria.
2. Design a Medallion architecture (Bronze / Silver / Gold) for Microsoft Fabric
   that satisfies the requirements — including entity names, key columns, grain,
   relationships, and partitioning strategy for each layer.
3. Commit repository scaffolding to a Git feature branch named
   `feature/wi-<id>-<slug>` using the `ado_commit_files` tool. The scaffold must
   include:
     - `docs/architecture/wi-<id>/README.md`  — executive summary
     - `src/schemas/bronze/<entity>.json`      — raw schema definitions
     - `src/schemas/silver/<entity>.json`      — cleansed schema definitions
     - `src/schemas/gold/<entity>.json`        — business-layer schema definitions
4. Create a detailed wiki page at `/architecture/wi-<id>-<slug>` using
   `ado_create_wiki_page` covering: background, data model diagrams (Mermaid
   ER syntax), layer descriptions, SLA & latency requirements, and open questions.
5. Update the work item description with a summary and links using
   `ado_update_work_item`.

Design principles to apply:
  • Bronze: immutable, raw, full-fidelity copy of the source. Delta Lake, append-only.
  • Silver: conformed, deduplicated, type-safe. Delta Lake with schema enforcement.
  • Gold: business-oriented aggregates optimised for DirectLake Power BI connections.
  • All tables use Delta format on Microsoft Fabric OneLake.
  • Partition by ingestion date at Bronze; by business key at Silver and Gold.

Output a concise summary when done, listing every file committed and the wiki page URL.
"""


class DataArchitectAgent(BaseAgent):
    name = "Data Architect Agent"
    system_prompt = _SYSTEM_PROMPT
    tools = [
        t for t in ADO_TOOLS
        if t["name"] in {
            "ado_get_work_item",
            "ado_update_work_item",
            "ado_create_wiki_page",
            "ado_get_wiki_page",
            "ado_commit_files",
            "ado_create_pull_request",
        }
    ] + [
        t for t in TEAMS_TOOLS
        if t["name"] == "teams_send_message"
    ]

    async def _dispatch(self, tool_name: str, tool_input: dict) -> Any:
        if tool_name.startswith("ado_"):
            return await execute_ado_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("teams_"):
            return await execute_teams_tool(self.settings, tool_name, tool_input)
        raise ValueError(f"DataArchitectAgent: unknown tool '{tool_name}'")
