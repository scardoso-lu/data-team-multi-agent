# data-team-multi-agent

Event-driven, multi-agent data engineering team orchestrated by an Azure DevOps
Kanban board. Each Kanban column is an agent's workspace. Agents claim work items,
perform their specialised work using Microsoft platform tools, then block at a
Human-in-the-Loop (HITL) approval gate (Teams Adaptive Card) before the item
advances to the next column.

## Architecture

```
ADO Kanban board (state machine)
│
├─ 01 - Architecture   → DataArchitectAgent   → ADO Wiki + Git scaffolding
├─ 02 - Engineering    → DataEngineerAgent    → Fabric Notebooks (PySpark) + Pipelines
├─ 03 - QA & Testing   → QAEngineerAgent      → pytest + PySpark DQ assertions
├─ 04 - Analytics & BI → DataAnalystAgent     → Power BI Semantic Model + Purview dict
└─ 05 - Governance     → DataStewardAgent     → Full audit → Teams summary → Done
         │
         └─ Every stage: Teams Adaptive Card approval gate before item advances
```

### Agent independence invariants

- Each agent constructs its own `anthropic.Anthropic` client — no shared client.
- All five columns are polled concurrently per tick (`asyncio.gather`).
- `_process_item` runs as a background `asyncio.Task` — a 24-hour HITL wait in
  one column has zero effect on any other column.
- An `_in_flight` set in `StateLoop` prevents double-dispatch across ticks.

### Technology stack

| Concern | Technology |
|---|---|
| Agent intelligence | Anthropic Claude (`claude-opus-4-7`) via `anthropic` SDK |
| Auth | `azure-identity` `ClientSecretCredential` (all Microsoft services) |
| ADO Boards / Git / Wiki | `azure-devops` Python SDK |
| Teams messages + Adaptive Cards | Microsoft Graph API (`msgraph-sdk`) |
| Fabric Notebooks + Pipelines | Fabric REST API (`api.fabric.microsoft.com/v1`) |
| Data Engineer execution | Apache Spark (PySpark) in Fabric Notebooks; Delta Lake on OneLake |
| QA testing | pytest in Fabric Notebooks + PySpark DataQualityRunner |
| Data governance | Microsoft Purview Atlas v2 REST API |
| HITL approval state | Azure Table Storage |
| Webhook receiver | FastAPI (swap for Azure Function in production) |

## Project layout

```
main.py                                  # Entry point: FastAPI + StateLoop
pyproject.toml                           # Dependencies and build config
.env.example                             # All required environment variables

src/data_team/
  orchestrator/
    config.py                            # Pydantic Settings (lru_cache singleton)
    models.py                            # WorkItem, ApprovalRequest, AgentResult
    state_loop.py                        # Async poll loop — concurrent column scanning

  tools/                                 # Anthropic tool schemas + implementations
    ado.py                               # ADO Boards, Git commits, Wiki CRUD
    teams.py                             # Graph API messages + Adaptive Cards
    fabric.py                            # Lakehouse, Notebook, Pipeline, SemanticModel
    purview.py                           # Atlas v2 asset registration, lineage, glossary

  agents/
    base.py                              # BaseAgent: agentic loop + prompt caching
    architect.py                         # Column 01 — schema design, wiki, scaffolding
    engineer.py                          # Column 02 — PySpark medallion implementation
    qa.py                                # Column 03 — data quality + pytest harness
    analyst.py                           # Column 04 — semantic model + Purview dict
    steward.py                           # Column 05 — audit checklist + final summary

  hitl/
    approval_gate.py                     # Azure Table Storage PENDING→APPROVED/REJECTED
    webhook.py                           # FastAPI router: POST /webhook/approve

tests/
  test_state_loop.py                     # Unit tests (fully mocked, no cloud creds)
```

## Setup

### 1. Python environment

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env — fill in all required values (ADO, Azure AD, Teams, Fabric, Purview, Anthropic)
```

Required variables (see `.env.example` for the full list):

| Variable | Description |
|---|---|
| `ADO_ORG_URL` | `https://dev.azure.com/your-org` |
| `ADO_PAT` | Personal Access Token (Work Items RW, Code RW, Wiki RW) |
| `ADO_PROJECT` | ADO project name |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_CLIENT_ID` | App registration client ID |
| `AZURE_CLIENT_SECRET` | App registration secret |
| `TEAMS_TEAM_ID` | Teams team GUID |
| `TEAMS_CHANNEL_ID` | Teams channel GUID |
| `APPROVAL_WEBHOOK_URL` | Public HTTPS URL for Teams card callbacks |
| `APPROVAL_STORAGE_URL` | `https://<account>.table.core.windows.net` |
| `FABRIC_WORKSPACE_ID` | Fabric workspace GUID |
| `PURVIEW_ENDPOINT` | `https://<account>.purview.azure.com` |
| `ANTHROPIC_API_KEY` | Anthropic API key |

### 3. Azure Table Storage

The HITL approval gate uses a table named `agentapprovals` in the storage account
pointed to by `APPROVAL_STORAGE_URL`. The table is created automatically on first
run if it does not exist.

### 4. ADO Kanban board

Create five columns on your ADO board matching the names in `.env` exactly:

```
01 - Architecture | 02 - Engineering | 03 - QA & Testing | 04 - Analytics & BI | 05 - Governance & Review | Done
```

### 5. HITL webhook (dev)

Teams Adaptive Card buttons POST to `APPROVAL_WEBHOOK_URL`. In dev, expose the
local FastAPI server with [Azure Dev Tunnels](https://learn.microsoft.com/azure/developer/dev-tunnels/):

```bash
devtunnel host --port 8080
# Set APPROVAL_WEBHOOK_URL to the tunnel URL + /webhook/approve
```

In production, replace the FastAPI router (`hitl/webhook.py`) with an Azure
Function (HTTP trigger, Python v2) — the `ApprovalGate.resolve()` contract is
unchanged.

## Running

```bash
python main.py
```

This starts:
- FastAPI on `0.0.0.0:8080` (webhook receiver + `/health`)
- StateLoop polling ADO every `POLL_INTERVAL_SECONDS` (default 30)

Health check: `curl http://localhost:8080/health`

## Testing

```bash
pytest                    # all tests
pytest -v                 # verbose
pytest -k "independent"   # specific test
```

Tests mock all external I/O — no cloud credentials required. Because
`_process_item` runs as a background asyncio.Task, tests call the helper
`await _drain(loop)` after `_tick()` to await pending tasks before asserting.

## Adding a new agent

1. Create `src/data_team/agents/my_agent.py` subclassing `BaseAgent`.
2. Declare `name`, `system_prompt`, and `tools` as class variables.
3. Implement `_dispatch(tool_name, tool_input)` routing to the relevant tool modules.
4. Add an entry to `_PIPELINE_SPEC` in `orchestrator/state_loop.py`.
5. Create the matching column on the ADO board.

Agents must only accept `settings: Settings` in `__init__` (enforced by
`test_each_agent_class_accepts_only_settings`).

## Key design decisions

**Why `asyncio.create_task` for `_process_item`?**
A HITL gate can block for up to `APPROVAL_TIMEOUT_HOURS` (default 24 h). Firing
each item as a background task lets all five columns operate simultaneously.

**Why Azure Table Storage for approval state?**
It is process-safe (multiple replicas can read/write), persistent across restarts,
and native to the Microsoft stack without requiring a message broker.

**Why PySpark (not T-SQL) for Silver/Gold transformations?**
Delta MERGE INTO, SCD Type 2, and CDC patterns need a DataFrame API. T-SQL on
the SQL Analytics Endpoint is still used for Gold-layer DDL views served to
Power BI via DirectLake.

**Why pytest (not a proprietary DQ framework) for QA?**
pytest is pip-installable on Fabric Spark custom environments and is used in
Microsoft's own Fabric sample repos. The custom PySpark `DataQualityRunner` uses
Spark aggregations directly — no third-party dependency.
