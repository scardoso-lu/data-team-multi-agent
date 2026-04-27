"""
Data Engineer Agent — Column: 02 - Engineering

Responsibilities:
  • Read the architecture wiki page and schema files committed by the Architect.
  • Provision Bronze, Silver, and Gold Lakehouses in Microsoft Fabric (if not
    already present).
  • Create PySpark Fabric Notebooks for each Medallion layer and commit the
    notebook source code to the ADO Git repo.
  • Create and run a Fabric Data Pipeline that orchestrates the notebooks in
    order (Bronze → Silver → Gold).
  • Commit all code to the feature branch and open a pull request.
  • Update the ADO work item with pipeline run IDs and artifact links.

Technology choices (see also fabric.py module docstring):
  • Execution  : Apache Spark (PySpark) in Microsoft Fabric Notebooks —
                 the native compute engine for Fabric Data Engineering.
  • Storage    : Delta Lake on OneLake — every Lakehouse table is Delta by
                 default; supports MERGE, OPTIMIZE, Z-ORDER, time-travel.
  • Pipelines  : Fabric Data Pipelines (Azure Data Factory engine embedded in
                 Fabric) — provides Copy Activity for Bronze ingestion and
                 Notebook Activity for Silver/Gold transformations.
"""

from __future__ import annotations

from typing import Any

from data_team.agents.base import BaseAgent
from data_team.tools.ado import ADO_TOOLS, execute_ado_tool
from data_team.tools.fabric import FABRIC_TOOLS, execute_fabric_tool
from data_team.tools.teams import TEAMS_TOOLS, execute_teams_tool

_SYSTEM_PROMPT = """\
You are the Data Engineer for a Microsoft Fabric data engineering team.
Your column on the Kanban board is "02 - Engineering".

You implement Medallion architectures on Microsoft Fabric using PySpark Notebooks
and Fabric Data Pipelines (Azure Data Factory engine).

When you receive a work item:
1. Use `ado_get_wiki_page` to read the architecture document at
   `/architecture/wi-<id>-<slug>` to understand the data model.
2. Use `fabric_list_items` to check which Lakehouses already exist.
3. If missing, create Bronze, Silver, and Gold Lakehouses using
   `fabric_create_lakehouse`.
4. Create PySpark Notebooks for each layer using `fabric_create_notebook`:
     - `bronze_<entity>_ingest.py`  : Structured Streaming / COPY INTO from source
     - `silver_<entity>_cleanse.py` : Schema enforcement, deduplication via Delta MERGE
     - `gold_<entity>_aggregate.py` : Business aggregation, partitioning for DirectLake
   Embed the actual PySpark code inside the notebook content. Use Delta Lake
   operations (MERGE INTO, OPTIMIZE, Z-ORDER) appropriately.
5. Create a Fabric Data Pipeline using `fabric_create_pipeline` that sequences:
     bronze notebook → silver notebook → gold notebook.
6. Run the pipeline using `fabric_run_pipeline` and verify it succeeds.
7. Commit all notebook source files to the ADO Git feature branch using
   `ado_commit_files` and open a pull request with `ado_create_pull_request`.
8. Update the work item via `ado_update_work_item` with pipeline IDs and run status.

PySpark coding standards:
  • All DataFrames must have explicit schemas (StructType).
  • Use Delta MERGE INTO for Silver upserts — never overwrite.
  • Apply OPTIMIZE + Z-ORDER BY (business key) on Gold tables after each run.
  • Log row counts and null rates before and after each transformation.
  • Never hard-code connection strings — read from Spark configs or
    `notebookutils.credentials`.

Output a concise summary when done, listing Lakehouse IDs, notebook IDs,
pipeline ID, PR number, and run status.
"""


class DataEngineerAgent(BaseAgent):
    name = "Data Engineer Agent"
    system_prompt = _SYSTEM_PROMPT
    tools = [
        t for t in ADO_TOOLS
        if t["name"] in {
            "ado_get_work_item",
            "ado_update_work_item",
            "ado_get_wiki_page",
            "ado_commit_files",
            "ado_create_pull_request",
        }
    ] + [
        t for t in FABRIC_TOOLS
        if t["name"] in {
            "fabric_list_items",
            "fabric_create_lakehouse",
            "fabric_create_notebook",
            "fabric_run_notebook",
            "fabric_create_pipeline",
            "fabric_run_pipeline",
        }
    ] + [
        t for t in TEAMS_TOOLS
        if t["name"] == "teams_send_message"
    ]

    async def _dispatch(self, tool_name: str, tool_input: dict) -> Any:
        if tool_name.startswith("ado_"):
            return await execute_ado_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("fabric_"):
            return await execute_fabric_tool(self.settings, tool_name, tool_input)
        if tool_name.startswith("teams_"):
            return await execute_teams_tool(self.settings, tool_name, tool_input)
        raise ValueError(f"DataEngineerAgent: unknown tool '{tool_name}'")
