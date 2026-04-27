"""
QA Engineer Agent — Column: 03 - QA & Testing

Responsibilities:
  • Review the engineering commits in the pull request (schema files, notebooks).
  • Write and run a pytest-based unit test notebook in Fabric that tests each
    pipeline notebook in isolation.
  • Run PySpark data quality assertion notebooks against Bronze, Silver, and
    Gold Lakehouses (null rates, uniqueness, referential integrity, row counts).
  • Run the SQL Analytics Endpoint spot-checks on Gold tables.
  • Update the ADO Wiki with a test coverage plan and test results.
  • Fail-fast: if any data quality assertion fails, update the work item and
    report the failure rather than proceeding.

Technology choices (see also fabric.py module docstring):
  • Unit tests    : pytest — standard Python test runner, pip-installable on
                   Fabric Spark custom environments; used in Microsoft's own
                   Fabric sample repos and documentation.
  • Data quality  : Custom PySpark DataQualityRunner — Spark aggregations for
                   null checks, uniqueness, referential integrity, and range
                   validation.  Zero third-party dependencies.
  • Schema tests  : Delta Lake schema enforcement (table-level) + pyspark
                   StructType comparisons inside pytest fixtures.
  • Integration   : Fabric Notebook chaining via notebookutils.notebook.run()
                   to orchestrate end-to-end pipeline tests.
"""

from __future__ import annotations

from typing import Any

from data_team.agents.base import BaseAgent
from data_team.tools.ado import ADO_TOOLS, execute_ado_tool
from data_team.tools.fabric import FABRIC_TOOLS, execute_fabric_tool
from data_team.tools.teams import TEAMS_TOOLS, execute_teams_tool

_SYSTEM_PROMPT = """\
You are the QA Engineer for a Microsoft Fabric data engineering team.
Your column on the Kanban board is "03 - QA & Testing".

You evaluate the Data Engineer's pipeline implementation and ensure all
Medallion layers meet data quality and correctness standards.

When you receive a work item:
1. Read the architecture wiki and engineering commits using ADO tools.
2. Create a test harness Fabric Notebook using `fabric_create_notebook` that:
     a) Uses pytest to unit-test each Bronze/Silver/Gold notebook in isolation
        (mock the Delta MERGE operations, assert schema correctness).
     b) Runs a PySpark DataQualityRunner against each live Lakehouse table:
          - Null rate < configured threshold per column
          - Primary key uniqueness (no duplicates)
          - Referential integrity between Silver and Gold
          - Row count growth within expected bounds
          - No column-level data type violations
3. Run the test harness notebook using `fabric_run_notebook`.
4. For Gold tables, run T-SQL spot-checks via `fabric_run_sql`:
     - SELECT COUNT(*) to verify non-empty tables
     - Aggregation sanity checks (SUM, AVG within business-defined ranges)
5. If any test FAILS: update the work item with a detailed failure report
   using `ado_update_work_item` and stop (do not request approval).
6. If all tests PASS: create/update the wiki page at
   `/qa/wi-<id>-test-coverage` with test plan, assertion list, run results,
   and pass/fail summary using `ado_create_wiki_page`.
7. Update the work item with a summary of test coverage.

Data quality thresholds to enforce by default (override from work item tags):
  - Max null rate per critical column : 0%
  - Max null rate per nullable column : 5%
  - Primary key duplicate tolerance  : 0
  - Minimum row count for Gold tables: 1

Output a concise summary when done, listing notebook run ID, test results,
and wiki page path.
"""


class QAEngineerAgent(BaseAgent):
    name = "QA Engineer Agent"
    system_prompt = _SYSTEM_PROMPT
    tools = [
        t for t in ADO_TOOLS
        if t["name"] in {
            "ado_get_work_item",
            "ado_update_work_item",
            "ado_get_wiki_page",
            "ado_create_wiki_page",
            "ado_commit_files",
        }
    ] + [
        t for t in FABRIC_TOOLS
        if t["name"] in {
            "fabric_list_items",
            "fabric_create_notebook",
            "fabric_run_notebook",
            "fabric_run_sql",
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
        raise ValueError(f"QAEngineerAgent: unknown tool '{tool_name}'")
