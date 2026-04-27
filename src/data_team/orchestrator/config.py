"""
Centralised configuration — all values sourced from environment / .env file.
Use `get_settings()` everywhere (cached singleton via lru_cache).
"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Azure DevOps ──────────────────────────────────────────────────────────
    ado_org_url: str = Field(..., description="https://dev.azure.com/your-org")
    ado_pat: str = Field(..., description="Personal Access Token — Work Items RW, Code RW, Wiki RW")
    ado_project: str
    ado_repo_name: str = "data-platform"
    ado_wiki_id: str = Field(..., description="Usually <project>.wiki")

    # Board column names — must match ADO board column labels exactly
    col_architecture: str = "01 - Architecture"
    col_engineering: str = "02 - Engineering"
    col_qa: str = "03 - QA & Testing"
    col_analytics: str = "04 - Analytics & BI"
    col_governance: str = "05 - Governance & Review"
    col_done: str = "Done"

    # ── Microsoft Entra ID ────────────────────────────────────────────────────
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str

    # ── Teams ─────────────────────────────────────────────────────────────────
    teams_team_id: str
    teams_channel_id: str
    approval_webhook_url: str = Field(
        ..., description="HTTPS endpoint that receives Adaptive Card approval POSTs"
    )

    # ── Microsoft Fabric ──────────────────────────────────────────────────────
    fabric_workspace_id: str
    fabric_bronze_lakehouse_id: str = ""
    fabric_silver_lakehouse_id: str = ""
    fabric_gold_lakehouse_id: str = ""

    # ── Microsoft Purview ─────────────────────────────────────────────────────
    purview_endpoint: str = Field(..., description="https://<account>.purview.azure.com")
    purview_collection: str = "root-collection-name"

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str
    anthropic_model: str = "claude-opus-4-7"

    # ── Orchestrator behaviour ────────────────────────────────────────────────
    poll_interval_seconds: int = 30
    approval_timeout_hours: int = 24
    bot_display_name: str = "Data Team Agent Bot"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
