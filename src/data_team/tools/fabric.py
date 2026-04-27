"""
Microsoft Fabric tools — Lakehouses, Notebooks, Spark Jobs, Data Pipelines,
Semantic Models, and Power BI report publishing.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA ENGINEER — Technology Choices
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Execution engine : Apache Spark via PySpark inside Microsoft Fabric Notebooks.
  Spark is the *native* compute engine for Fabric's Data Engineering workload —
  it ships built-in with every Fabric capacity and requires zero infrastructure
  setup.  All Lakehouse tables are stored in Delta Lake format on OneLake
  (Fabric's unified storage layer), so Delta operations (MERGE INTO, OPTIMIZE,
  Z-ORDER BY, VACUUM) work out of the box without installing extra libraries.

Medallion implementation:
  • Bronze  — raw COPY INTO / ADLS Gen2 auto-load via Spark Structured Streaming
              or Fabric Data Pipelines (Copy Activity), stored as Delta on OneLake.
  • Silver  — PySpark DataFrames with schema enforcement, deduplication
              (dropDuplicates + Delta MERGE), and type-casting notebooks.
  • Gold    — PySpark aggregation notebooks producing wide, denormalized Delta
              tables optimised for DirectLake Power BI connections.

Orchestration : Fabric Data Pipelines (the ADFv2 engine embedded in Fabric).
  Agents submit notebooks and pipeline runs through the Fabric REST API
  (api.fabric.microsoft.com/v1) authenticated via azure-identity tokens.

Why PySpark over T-SQL for Silver/Gold?  Delta MERGE patterns (SCD Type 2,
CDC) need the expressiveness of a DataFrame API; T-SQL on the SQL Analytics
Endpoint is excellent for ad-hoc queries and Gold-layer views served to
Power BI via DirectLake, so both are used in concert.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QA ENGINEER — Technology Choices
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Unit tests   : pytest — the standard Python test runner, fully supported inside
  Fabric Notebooks via `notebookutils.notebook.run()` and pip-installable on
  Fabric's Spark pool custom environments.  Microsoft's own Fabric documentation
  and sample repos use pytest for notebook unit testing.

Data quality : PySpark-native assertion framework (custom DataQualityRunner in
  this codebase).  Leverages Spark's built-in aggregations for null checks,
  uniqueness, referential integrity, and range validation against the Delta
  tables.  No third-party DQ library is imported; the framework is expressed
  as PySpark transformations so it runs on the same Spark pool as the pipelines
  with no additional cost or setup.

Schema validation : Delta Lake schema enforcement (table-level) + pyspark
  StructType comparisons in unit tests to catch breaking schema changes before
  promotion to Silver / Gold.

Integration tests : Fabric Notebook chaining — the QA agent submits a
  "test harness" notebook to Fabric that calls `notebookutils.notebook.run()`
  for each pipeline stage notebook and asserts the output Delta table row counts
  and statistical profiles.

Declarative rules : Microsoft Fabric Data Quality (preview feature in the
  Fabric Data Factory workload) — YAML-based rule definitions that run as
  Spark activities and write quality scores to a monitoring Lakehouse table.
  These scores are then surfaced in Microsoft Purview's data quality tab.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from azure.identity import ClientSecretCredential

from data_team.orchestrator.config import Settings

# ── Anthropic Tool Schemas ─────────────────────────────────────────────────────

FABRIC_TOOLS: list[dict[str, Any]] = [
    # ── Lakehouse ─────────────────────────────────────────────────────────────
    {
        "name": "fabric_create_lakehouse",
        "description": (
            "Create a new Lakehouse item inside the configured Fabric workspace. "
            "Used by the Data Architect to provision Bronze, Silver, and Gold Lakehouses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": "Human-readable name, e.g. 'bronze_lakehouse'.",
                },
                "description": {"type": "string", "default": ""},
            },
            "required": ["display_name"],
        },
    },
    # ── Notebooks ─────────────────────────────────────────────────────────────
    {
        "name": "fabric_create_notebook",
        "description": (
            "Create a new Fabric Notebook (PySpark) in the workspace and optionally "
            "attach it to a Lakehouse. The notebook content is provided as a base64-encoded "
            "Jupyter notebook JSON string (ipynb format)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {"type": "string"},
                "description": {"type": "string", "default": ""},
                "notebook_content_base64": {
                    "type": "string",
                    "description": "Base64-encoded .ipynb JSON string.",
                },
                "default_lakehouse_id": {
                    "type": "string",
                    "description": "Lakehouse item ID to mount as the default Lakehouse.",
                    "default": "",
                },
            },
            "required": ["display_name", "notebook_content_base64"],
        },
    },
    {
        "name": "fabric_run_notebook",
        "description": (
            "Submit a Fabric Notebook for execution as a Spark job and wait for "
            "completion.  Returns the job status and any output parameters "
            "the notebook was configured to expose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notebook_id": {
                    "type": "string",
                    "description": "Fabric item ID of the notebook to run.",
                },
                "parameters": {
                    "type": "object",
                    "description": "Key-value pairs injected as notebook parameters.",
                    "additionalProperties": True,
                    "default": {},
                },
                "timeout_minutes": {
                    "type": "integer",
                    "default": 60,
                    "description": "Maximum wait time before treating the run as failed.",
                },
            },
            "required": ["notebook_id"],
        },
    },
    # ── Data Pipelines ────────────────────────────────────────────────────────
    {
        "name": "fabric_create_pipeline",
        "description": (
            "Create a Fabric Data Pipeline (Azure Data Factory engine) in the workspace. "
            "The pipeline definition is provided as a JSON string conforming to the "
            "ADF pipeline JSON schema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {"type": "string"},
                "pipeline_definition_json": {
                    "type": "string",
                    "description": "ADF-compatible pipeline JSON definition.",
                },
            },
            "required": ["display_name", "pipeline_definition_json"],
        },
    },
    {
        "name": "fabric_run_pipeline",
        "description": (
            "Trigger a Fabric Data Pipeline run and wait for it to complete. "
            "Returns the run status and any error messages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "string"},
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                    "default": {},
                },
                "timeout_minutes": {"type": "integer", "default": 120},
            },
            "required": ["pipeline_id"],
        },
    },
    # ── Semantic Models & Power BI ────────────────────────────────────────────
    {
        "name": "fabric_create_semantic_model",
        "description": (
            "Create a Power BI Semantic Model (formerly Dataset) in the Fabric workspace "
            "from a TMSL/TMDL definition string. Used by the Data Analyst to build "
            "the Gold-layer semantic layer for DirectLake reporting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {"type": "string"},
                "tmdl_definition": {
                    "type": "string",
                    "description": (
                        "Tabular Model Definition Language (TMDL) or TMSL JSON string "
                        "defining tables, measures, hierarchies, and relationships."
                    ),
                },
            },
            "required": ["display_name", "tmdl_definition"],
        },
    },
    {
        "name": "fabric_deploy_report",
        "description": (
            "Publish a Power BI report (.pbix or thin-report JSON) to the Fabric workspace "
            "and bind it to an existing Semantic Model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "display_name": {"type": "string"},
                "semantic_model_id": {"type": "string"},
                "report_definition_json": {
                    "type": "string",
                    "description": "Thin-report JSON definition (report.json from a PBIP folder).",
                },
            },
            "required": ["display_name", "semantic_model_id", "report_definition_json"],
        },
    },
    # ── Delta Lake / SQL Analytics ────────────────────────────────────────────
    {
        "name": "fabric_run_sql",
        "description": (
            "Execute a T-SQL statement against a Lakehouse SQL Analytics Endpoint "
            "or Fabric Warehouse. Use for DDL (CREATE VIEW, ALTER TABLE) on the "
            "Gold layer or for data quality spot-checks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lakehouse_id": {"type": "string"},
                "sql": {
                    "type": "string",
                    "description": "T-SQL statement to execute.",
                },
            },
            "required": ["lakehouse_id", "sql"],
        },
    },
    # ── Workspace introspection ───────────────────────────────────────────────
    {
        "name": "fabric_list_items",
        "description": "List all items in the Fabric workspace, optionally filtered by item type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "enum": [
                        "Lakehouse", "Notebook", "DataPipeline",
                        "SemanticModel", "Report", "Warehouse",
                    ],
                    "description": "Filter to a specific Fabric item type.",
                },
            },
            "required": [],
        },
    },
]

# ── Fabric REST API helpers ────────────────────────────────────────────────────

_FABRIC_BASE = "https://api.fabric.microsoft.com/v1"
_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def _token(settings: Settings) -> str:
    cred = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    return cred.get_token(_FABRIC_SCOPE).token


def _headers(settings: Settings) -> dict:
    return {
        "Authorization": f"Bearer {_token(settings)}",
        "Content-Type": "application/json",
    }


def _workspace_url(settings: Settings, path: str = "") -> str:
    return f"{_FABRIC_BASE}/workspaces/{settings.fabric_workspace_id}{path}"


def _poll_long_running(
    settings: Settings, operation_url: str, timeout_minutes: int = 60
) -> dict:
    """Poll a Fabric long-running operation URL until terminal state or timeout."""
    deadline = time.time() + timeout_minutes * 60
    interval = 5
    while time.time() < deadline:
        with httpx.Client() as client:
            r = client.get(operation_url, headers=_headers(settings), timeout=15)
            r.raise_for_status()
            data = r.json()
        status = data.get("status", "").lower()
        if status in ("succeeded", "failed", "cancelled"):
            return data
        time.sleep(interval)
        interval = min(interval * 2, 60)
    return {"status": "timed_out"}


# ── Tool implementations ───────────────────────────────────────────────────────


def fabric_list_items(settings: Settings, item_type: str | None = None) -> dict:
    params = f"?type={item_type}" if item_type else ""
    with httpx.Client() as client:
        r = client.get(
            _workspace_url(settings, f"/items{params}"),
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def fabric_create_lakehouse(
    settings: Settings, display_name: str, description: str = ""
) -> dict:
    payload = {
        "displayName": display_name,
        "type": "Lakehouse",
        "description": description,
    }
    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, "/items"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


def fabric_create_notebook(
    settings: Settings,
    display_name: str,
    notebook_content_base64: str,
    description: str = "",
    default_lakehouse_id: str = "",
) -> dict:
    payload: dict[str, Any] = {
        "displayName": display_name,
        "type": "Notebook",
        "description": description,
        "definition": {
            "format": "ipynb",
            "parts": [
                {
                    "path": "notebook-content.py",
                    "payload": notebook_content_base64,
                    "payloadType": "InlineBase64",
                }
            ],
        },
    }
    if default_lakehouse_id:
        payload["properties"] = {"defaultLakehouse": {"id": default_lakehouse_id}}

    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, "/items"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


def fabric_run_notebook(
    settings: Settings,
    notebook_id: str,
    parameters: dict | None = None,
    timeout_minutes: int = 60,
) -> dict:
    payload: dict[str, Any] = {}
    if parameters:
        payload["executionData"] = {"parameters": parameters}

    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, f"/items/{notebook_id}/jobs/instances?jobType=RunNotebook"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
        # 202 Accepted — Location header contains the polling URL
        operation_url = r.headers.get("Location", "")

    if operation_url:
        return _poll_long_running(settings, operation_url, timeout_minutes)
    return {"status": "submitted", "notebook_id": notebook_id}


def fabric_create_pipeline(
    settings: Settings, display_name: str, pipeline_definition_json: str
) -> dict:
    import base64, json as _json

    encoded = base64.b64encode(pipeline_definition_json.encode()).decode()
    payload = {
        "displayName": display_name,
        "type": "DataPipeline",
        "definition": {
            "parts": [
                {
                    "path": "pipeline-content.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        },
    }
    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, "/items"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


def fabric_run_pipeline(
    settings: Settings,
    pipeline_id: str,
    parameters: dict | None = None,
    timeout_minutes: int = 120,
) -> dict:
    payload: dict[str, Any] = {}
    if parameters:
        payload["parameters"] = parameters

    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, f"/items/{pipeline_id}/jobs/instances?jobType=Pipeline"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
        operation_url = r.headers.get("Location", "")

    if operation_url:
        return _poll_long_running(settings, operation_url, timeout_minutes)
    return {"status": "submitted", "pipeline_id": pipeline_id}


def fabric_create_semantic_model(
    settings: Settings, display_name: str, tmdl_definition: str
) -> dict:
    import base64

    encoded = base64.b64encode(tmdl_definition.encode()).decode()
    payload = {
        "displayName": display_name,
        "type": "SemanticModel",
        "definition": {
            "parts": [
                {
                    "path": "model.tmdl",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        },
    }
    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, "/items"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


def fabric_deploy_report(
    settings: Settings,
    display_name: str,
    semantic_model_id: str,
    report_definition_json: str,
) -> dict:
    import base64

    encoded = base64.b64encode(report_definition_json.encode()).decode()
    payload = {
        "displayName": display_name,
        "type": "Report",
        "definition": {
            "parts": [
                {
                    "path": "report.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ]
        },
        "properties": {"semanticModelId": semantic_model_id},
    }
    with httpx.Client() as client:
        r = client.post(
            _workspace_url(settings, "/items"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


def fabric_run_sql(settings: Settings, lakehouse_id: str, sql: str) -> dict:
    """
    Execute T-SQL via the Lakehouse SQL Analytics Endpoint using the
    Fabric Execute Queries REST API.
    """
    url = _workspace_url(settings, f"/lakehouses/{lakehouse_id}/queryEndpoint/execQuery")
    payload = {"query": sql}
    with httpx.Client() as client:
        r = client.post(url, json=payload, headers=_headers(settings), timeout=60)
        r.raise_for_status()
    return r.json()


# ── Unified dispatcher ────────────────────────────────────────────────────────


async def execute_fabric_tool(settings: Settings, tool_name: str, tool_input: dict) -> Any:
    dispatch = {
        "fabric_list_items":           lambda: fabric_list_items(settings, **tool_input),
        "fabric_create_lakehouse":     lambda: fabric_create_lakehouse(settings, **tool_input),
        "fabric_create_notebook":      lambda: fabric_create_notebook(settings, **tool_input),
        "fabric_run_notebook":         lambda: fabric_run_notebook(settings, **tool_input),
        "fabric_create_pipeline":      lambda: fabric_create_pipeline(settings, **tool_input),
        "fabric_run_pipeline":         lambda: fabric_run_pipeline(settings, **tool_input),
        "fabric_create_semantic_model":lambda: fabric_create_semantic_model(settings, **tool_input),
        "fabric_deploy_report":        lambda: fabric_deploy_report(settings, **tool_input),
        "fabric_run_sql":              lambda: fabric_run_sql(settings, **tool_input),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown Fabric tool: {tool_name}")
    return fn()
