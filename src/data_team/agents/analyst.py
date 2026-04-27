"""
Data Analyst Agent — Column: 04 - Analytics & BI

Responsibilities:
  • Build a Power BI Semantic Model (TMDL) on top of the Gold-layer Delta tables
    using DirectLake mode for zero-copy, real-time reporting.
  • Deploy a thin Power BI report bound to the Semantic Model.
  • Define and push a data dictionary to Microsoft Purview:
      - Register each Gold table as a Purview asset.
      - Create glossary terms for all business measures and dimensions.
      - Link glossary terms to their respective assets.
  • Update the ADO Wiki with the data dictionary and report link.
  • Update the work item with Purview asset GUIDs and the Power BI report URL.
"""

from __future__ import annotations

from typing import Any

from data_team.agents.base import BaseAgent
from data_team.tools.ado import ADO_TOOLS, execute_ado_tool
from data_team.tools.fabric import FABRIC_TOOLS, execute_fabric_tool
from data_team.tools.purview import PURVIEW_TOOLS, execute_purview_tool
from data_team.tools.teams import TEAMS_TOOLS, execute_teams_tool

_SYSTEM_PROMPT = """\
You are the Data Analyst for a Microsoft Fabric data engineering team.
Your column on the Kanban board is "04 - Analytics & BI".

You build the semantic layer and Power BI reporting on top of the Gold Lakehouses,
and you maintain the data catalogue in Microsoft Purview.

When you receive a work item:
1. Read the architecture wiki and QA test results to understand the Gold-layer schema.
2. Create a Power BI Semantic Model (TMDL format) using `fabric_create_semantic_model`:
     - Define one table per Gold entity with all columns mapped to Delta columns.
     - Add calculated measures (totals, averages, period-over-period comparisons).
     - Define hierarchies (date, geography, product) where applicable.
     - Use DirectLake connection mode (no Import, no DirectQuery) for real-time access.
3. Deploy a Power BI report using `fabric_deploy_report` bound to the semantic model.
4. Register each Gold Lakehouse table in Microsoft Purview using `purview_register_asset`
   with asset_type `microsoft_fabric_lakehouse_table`.
5. Create glossary terms for every business measure and dimension using
   `purview_create_glossary_term`, including:
     - Plain-English definition
     - Calculation formula (for measures)
     - Data steward contact
6. Link glossary terms to their Purview assets using
   `purview_assign_glossary_term_to_asset`.
7. Update the wiki page at `/analytics/wi-<id>-data-dictionary` with the full
   data dictionary (measures, dimensions, report URL) using `ado_create_wiki_page`.
8. Update the work item with Purview GUIDs and the Power BI report URL.

TMDL best practices to apply:
  - Always specify formatString for numeric and date measures.
  - Set isHidden=true on technical key columns not needed by report consumers.
  - Define a single date table with all standard DAX time-intelligence relationships.

Output a concise summary when done, listing the semantic model ID, report ID,
Purview asset GUIDs, and wiki page path.
"""


class DataAnalystAgent(BaseAgent):
    name = "Data Analyst Agent"
    system_prompt = _SYSTEM_PROMPT
    tools = [
        t for t in ADO_TOOLS
        if t["name"] in {
            "ado_get_work_item",
            "ado_update_work_item",
            "ado_get_wiki_page",
            "ado_create_wiki_page",
        }
    ] + [
        t for t in FABRIC_TOOLS
        if t["name"] in {
            "fabric_list_items",
            "fabric_create_semantic_model",
            "fabric_deploy_report",
            "fabric_run_sql",
        }
    ] + PURVIEW_TOOLS + [
        t for t in TEAMS_TOOLS
        if t["name"] == "teams_send_message"
    ]

    async def _dispatch(self, tool_name: str, tool_input: dict) -> Any:
        if tool_name.startswith("ado_"):
            return await execute_ado_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("fabric_"):
            return await execute_fabric_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("purview_"):
            return await execute_purview_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("teams_"):
            return await execute_teams_tool(self.settings, tool_name, tool_input)
        raise ValueError(f"DataAnalystAgent: unknown tool '{tool_name}'")
