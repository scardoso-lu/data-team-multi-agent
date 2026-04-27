"""
Microsoft Purview tools — asset registration, glossary, lineage, and
data quality score retrieval.

All calls use the Purview REST APIs directly via httpx + azure-identity
(ClientSecretCredential).  The app registration must have the following
Purview role assignments:
  - Data Curator  (create/update assets, glossary terms)
  - Data Reader   (search, browse)

Purview API base:  https://<account>.purview.azure.com
Catalog API:       /catalog/api/   (Atlas v2 compatible)
"""

from __future__ import annotations

from typing import Any

import httpx
from azure.identity import ClientSecretCredential

from data_team.orchestrator.config import Settings

# ── Anthropic Tool Schemas ─────────────────────────────────────────────────────

PURVIEW_TOOLS: list[dict[str, Any]] = [
    {
        "name": "purview_register_asset",
        "description": (
            "Register or update a data asset in Microsoft Purview. "
            "Typically called by the Data Analyst for Gold-layer Delta tables "
            "and by the Data Steward during final governance review. "
            "Accepts an Apache Atlas entity definition."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "qualified_name": {
                    "type": "string",
                    "description": (
                        "Globally unique asset identifier following Purview naming convention, "
                        "e.g. 'mssql://fabric/workspace/<id>/lakehouse/gold/customer_dim'."
                    ),
                },
                "display_name": {"type": "string"},
                "asset_type": {
                    "type": "string",
                    "enum": [
                        "azure_datalake_gen2_path",
                        "microsoft_fabric_lakehouse_table",
                        "microsoft_fabric_lakehouse",
                        "powerbi_dataset",
                        "powerbi_report",
                    ],
                    "description": "Purview entity type name.",
                },
                "description": {"type": "string", "default": ""},
                "custom_attributes": {
                    "type": "object",
                    "description": "Additional Atlas attribute key-value pairs.",
                    "additionalProperties": True,
                    "default": {},
                },
                "collection_name": {
                    "type": "string",
                    "description": "Target Purview collection. Defaults to workspace collection.",
                    "default": "",
                },
            },
            "required": ["qualified_name", "display_name", "asset_type"],
        },
    },
    {
        "name": "purview_create_glossary_term",
        "description": (
            "Create a new business glossary term in Microsoft Purview. "
            "Used by the Data Analyst to document the data dictionary "
            "alongside Gold-layer semantic model deployment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Business term name."},
                "definition": {
                    "type": "string",
                    "description": "Plain-English definition of the term.",
                },
                "long_description": {
                    "type": "string",
                    "description": "Extended context, examples, calculation logic.",
                    "default": "",
                },
                "acronym": {"type": "string", "default": ""},
                "steward_email": {
                    "type": "string",
                    "description": "Email of the assigned data steward.",
                    "default": "",
                },
                "experts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of subject-matter expert emails.",
                    "default": [],
                },
            },
            "required": ["name", "definition"],
        },
    },
    {
        "name": "purview_assign_glossary_term_to_asset",
        "description": "Associate one or more glossary terms with a registered Purview asset.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_guid": {
                    "type": "string",
                    "description": "Purview entity GUID returned by purview_register_asset.",
                },
                "term_guids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Purview glossary term GUIDs.",
                },
            },
            "required": ["asset_guid", "term_guids"],
        },
    },
    {
        "name": "purview_set_lineage",
        "description": (
            "Record a data lineage relationship between a source and target asset. "
            "Represents one stage of the Medallion pipeline "
            "(e.g. Bronze → Silver transformation)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_guid": {
                    "type": "string",
                    "description": "Purview GUID of the upstream (source) entity.",
                },
                "target_guid": {
                    "type": "string",
                    "description": "Purview GUID of the downstream (target) entity.",
                },
                "process_name": {
                    "type": "string",
                    "description": (
                        "Name of the transformation process, "
                        "e.g. 'silver_customer_notebook_run'."
                    ),
                },
                "process_qualified_name": {
                    "type": "string",
                    "description": "Unique qualified name for the process entity.",
                },
            },
            "required": ["source_guid", "target_guid", "process_name", "process_qualified_name"],
        },
    },
    {
        "name": "purview_search_assets",
        "description": "Full-text search across all registered assets in Microsoft Purview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords or qualified name."},
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of results to return.",
                },
                "asset_type_filter": {
                    "type": "string",
                    "description": "Optional Purview entity type to filter by.",
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "purview_get_asset",
        "description": "Retrieve full details of a Purview asset by its GUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_guid": {"type": "string"},
            },
            "required": ["asset_guid"],
        },
    },
    {
        "name": "purview_validate_lineage_completeness",
        "description": (
            "Audit the Purview lineage graph for a given target asset and verify "
            "that all expected Medallion stages (Bronze → Silver → Gold) are recorded. "
            "Called by the Data Steward during final governance review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "gold_asset_guid": {
                    "type": "string",
                    "description": "Purview GUID of the Gold-layer target asset.",
                },
                "expected_stages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of expected upstream asset qualified names.",
                    "default": [],
                },
            },
            "required": ["gold_asset_guid"],
        },
    },
]

# ── Purview REST API helpers ───────────────────────────────────────────────────

_PURVIEW_SCOPE = "https://purview.azure.net/.default"


def _token(settings: Settings) -> str:
    cred = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    return cred.get_token(_PURVIEW_SCOPE).token


def _catalog_url(settings: Settings, path: str) -> str:
    return f"{settings.purview_endpoint}/catalog/api{path}"


def _headers(settings: Settings) -> dict:
    return {
        "Authorization": f"Bearer {_token(settings)}",
        "Content-Type": "application/json",
    }


# ── Tool implementations ───────────────────────────────────────────────────────


def purview_register_asset(
    settings: Settings,
    qualified_name: str,
    display_name: str,
    asset_type: str,
    description: str = "",
    custom_attributes: dict | None = None,
    collection_name: str = "",
) -> dict:
    entity: dict[str, Any] = {
        "typeName": asset_type,
        "attributes": {
            "qualifiedName": qualified_name,
            "name": display_name,
            "description": description,
            **(custom_attributes or {}),
        },
    }
    if collection_name or settings.purview_collection:
        entity["collectionId"] = collection_name or settings.purview_collection

    payload = {"entity": entity}
    with httpx.Client() as client:
        r = client.post(
            _catalog_url(settings, "/atlas/v2/entity"),
            json=payload,
            headers=_headers(settings),
            timeout=30,
        )
        r.raise_for_status()
    data = r.json()
    # Return the GUID assigned by Purview
    guid = (
        data.get("guidAssignments", {}).get("-1")
        or data.get("mutatedEntities", {}).get("CREATE", [{}])[0].get("guid", "")
    )
    return {"guid": guid, "qualified_name": qualified_name, "display_name": display_name}


def purview_create_glossary_term(
    settings: Settings,
    name: str,
    definition: str,
    long_description: str = "",
    acronym: str = "",
    steward_email: str = "",
    experts: list[str] | None = None,
) -> dict:
    term: dict[str, Any] = {
        "name": name,
        "shortDescription": definition,
        "longDescription": long_description or definition,
        "abbreviation": acronym,
        "anchor": {"glossaryGuid": ""},  # Uses the default glossary
    }
    if steward_email:
        term["stewards"] = [{"id": steward_email}]
    if experts:
        term["experts"] = [{"id": e} for e in experts]

    with httpx.Client() as client:
        r = client.post(
            _catalog_url(settings, "/atlas/v2/glossary/term"),
            json=term,
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def purview_assign_glossary_term_to_asset(
    settings: Settings, asset_guid: str, term_guids: list[str]
) -> dict:
    with httpx.Client() as client:
        r = client.post(
            _catalog_url(settings, f"/atlas/v2/entity/guid/{asset_guid}/assignedTerms"),
            json=[{"guid": g} for g in term_guids],
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return {"asset_guid": asset_guid, "terms_assigned": len(term_guids)}


def purview_set_lineage(
    settings: Settings,
    source_guid: str,
    target_guid: str,
    process_name: str,
    process_qualified_name: str,
) -> dict:
    """
    Create a lineage-process entity (Atlas type: Process) linking source → target.
    """
    process_entity: dict[str, Any] = {
        "typeName": "Process",
        "attributes": {
            "qualifiedName": process_qualified_name,
            "name": process_name,
            "inputs": [{"guid": source_guid, "typeName": "DataSet"}],
            "outputs": [{"guid": target_guid, "typeName": "DataSet"}],
        },
    }
    with httpx.Client() as client:
        r = client.post(
            _catalog_url(settings, "/atlas/v2/entity"),
            json={"entity": process_entity},
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def purview_search_assets(
    settings: Settings,
    query: str,
    limit: int = 20,
    asset_type_filter: str = "",
) -> dict:
    payload: dict[str, Any] = {
        "keywords": query,
        "limit": limit,
        "filter": {"typeName": asset_type_filter} if asset_type_filter else {},
    }
    with httpx.Client() as client:
        r = client.post(
            _catalog_url(settings, "/search/query"),
            json=payload,
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def purview_get_asset(settings: Settings, asset_guid: str) -> dict:
    with httpx.Client() as client:
        r = client.get(
            _catalog_url(settings, f"/atlas/v2/entity/guid/{asset_guid}"),
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def purview_validate_lineage_completeness(
    settings: Settings,
    gold_asset_guid: str,
    expected_stages: list[str] | None = None,
) -> dict:
    """
    Walk the Purview lineage graph backwards from the Gold asset and check that
    each expected upstream stage (by qualified name) is present.
    """
    with httpx.Client() as client:
        r = client.get(
            _catalog_url(settings, f"/atlas/v2/lineage/{gold_asset_guid}"),
            params={"direction": "INPUT", "depth": 10},
            headers=_headers(settings),
            timeout=15,
        )
        r.raise_for_status()
    lineage = r.json()

    found_names: set[str] = {
        e.get("attributes", {}).get("qualifiedName", "")
        for e in lineage.get("guidEntityMap", {}).values()
    }

    missing: list[str] = []
    for stage in (expected_stages or []):
        if not any(stage in name for name in found_names):
            missing.append(stage)

    return {
        "gold_asset_guid": gold_asset_guid,
        "lineage_complete": len(missing) == 0,
        "missing_stages": missing,
        "all_upstream_assets": list(found_names),
    }


# ── Unified dispatcher ────────────────────────────────────────────────────────


async def execute_purview_tool(settings: Settings, tool_name: str, tool_input: dict) -> Any:
    dispatch = {
        "purview_register_asset":               lambda: purview_register_asset(settings, **tool_input),
        "purview_create_glossary_term":         lambda: purview_create_glossary_term(settings, **tool_input),
        "purview_assign_glossary_term_to_asset":lambda: purview_assign_glossary_term_to_asset(settings, **tool_input),
        "purview_set_lineage":                  lambda: purview_set_lineage(settings, **tool_input),
        "purview_search_assets":                lambda: purview_search_assets(settings, **tool_input),
        "purview_get_asset":                    lambda: purview_get_asset(settings, **tool_input),
        "purview_validate_lineage_completeness":lambda: purview_validate_lineage_completeness(settings, **tool_input),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown Purview tool: {tool_name}")
    return fn()
