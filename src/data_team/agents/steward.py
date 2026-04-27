"""
Data Steward Agent — Column: 05 - Governance & Review

Responsibilities (final gatekeeper):
  • Audit the end-to-end lifecycle: verify every expected artifact exists across
    the ADO Git repo, Wiki, Fabric workspace, and Purview catalogue.
  • Validate Purview lineage completeness from Bronze → Silver → Gold.
  • Confirm the Power BI report is deployed and the Semantic Model is live.
  • Post a rich final summary card to the Teams channel.
  • Mark the ADO work item as Done (System.State = "Done").
  • If any audit check fails: post a failure notification to Teams and halt
    without closing the work item — a human must resolve the gap.
"""

from __future__ import annotations

from typing import Any

from data_team.agents.base import BaseAgent
from data_team.tools.ado import ADO_TOOLS, execute_ado_tool
from data_team.tools.fabric import FABRIC_TOOLS, execute_fabric_tool
from data_team.tools.purview import PURVIEW_TOOLS, execute_purview_tool
from data_team.tools.teams import TEAMS_TOOLS, execute_teams_tool

_SYSTEM_PROMPT = """\
You are the Data Steward for a Microsoft Fabric data engineering team.
Your column on the Kanban board is "05 - Governance & Review".
You are the final gatekeeper before a work item is closed as Done.

Your audit checklist — verify ALL of the following before posting the final summary:

ADO Repository:
  ☐ Feature branch exists and contains Bronze / Silver / Gold notebook source files.
  ☐ A pull request exists and is in an approved or completed state.
  ☐ Architecture wiki page exists at /architecture/wi-<id>-*.
  ☐ QA wiki page exists at /qa/wi-<id>-test-coverage.
  ☐ Analytics wiki page / data dictionary exists at /analytics/wi-<id>-*.

Microsoft Fabric:
  ☐ Bronze, Silver, and Gold Lakehouses exist in the workspace.
  ☐ All three pipeline notebooks exist and their last run status is "Succeeded".
  ☐ Semantic Model and Report are deployed in the workspace.

Microsoft Purview:
  ☐ Each Gold table is registered as a Purview asset.
  ☐ Lineage chain Bronze → Silver → Gold is complete (use
    `purview_validate_lineage_completeness`).
  ☐ Glossary terms exist and are linked to Gold assets.

Workflow:
1. Retrieve full work item details with `ado_get_work_item`.
2. Run through each checklist item using the available tools.
3. If ANY item fails: post a detailed failure report to Teams using
   `teams_send_message` listing every failed check. Stop — do NOT close the item.
4. If ALL items pass: post the final rich summary card using
   `teams_send_final_summary` with links to the Purview assets and Power BI report.
5. Mark the work item as Done: call `ado_update_work_item` with
   `{"System.State": "Done"}`.

Output a concise audit report listing every check and its pass/fail status.
"""


class DataStewardAgent(BaseAgent):
    name = "Data Steward Agent"
    system_prompt = _SYSTEM_PROMPT
    tools = (
        ADO_TOOLS
        + [
            t for t in FABRIC_TOOLS
            if t["name"] in {
                "fabric_list_items",
                "fabric_run_sql",
            }
        ]
        + PURVIEW_TOOLS
        + TEAMS_TOOLS
    )

    async def _dispatch(self, tool_name: str, tool_input: dict) -> Any:
        if tool_name.startswith("ado_"):
            return await execute_ado_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("fabric_"):
            return await execute_fabric_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("purview_"):
            return await execute_purview_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("teams_"):
            return await execute_teams_tool(self.settings, tool_name, tool_input)
        raise ValueError(f"DataStewardAgent: unknown tool '{tool_name}'")
