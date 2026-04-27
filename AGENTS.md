# Multi-Agent Data Engineering Team

## Purpose
This repository contains a Python prototype of a multi-agent data engineering workflow. Five role-specific agents poll Azure DevOps (ADO) board columns, perform placeholder work for their lifecycle stage, send Microsoft Teams notifications or approval requests, and move work items to the next column.

The intended lifecycle is defined in `config/default.json` under each agent's `column` and `next_column` values.

## Current Repository Layout

```text
.
├── agents/
│   ├── data_architect/
│   ├── data_engineer/
│   ├── qa_engineer/
│   ├── data_analyst/
│   └── data_steward/
├── shared_skills/
│   ├── ado_integration/
│   ├── approval_server/
│   ├── fabric_integration/
│   ├── purview_integration/
│   └── teams_integration/
├── tests/
├── config/
├── harness/
├── docker-compose.yml
├── pyproject.toml
├── AGENTS.md
├── LICENSE
└── README.md
```

Each agent directory currently contains:

- `app.py`: the agent class and infinite polling loop.
- `skill_loader.py`: dynamic loader for modules mounted at `/app/shared_skills`.
- `SKILLS.md`: role-specific skill documentation.
- `Dockerfile`: builds the container for that agent.
- `entrypoint.sh`: safely handles optional CLI tool environment variables before running the agent.

## Agents

| Agent | Main class | Config key |
| --- | --- | --- |
| Data Architect | `DataArchitectAgent` | `data_architect` |
| Data Engineer | `DataEngineerAgent` | `data_engineer` |
| QA Engineer | `QAEngineerAgent` | `qa_engineer` |
| Data Analyst | `DataAnalystAgent` | `data_analyst` |
| Data Steward | `DataStewardAgent` | `data_steward` |

All agents follow the same broad pattern:

1. Load shared skills with `SkillLoader`.
2. Poll ADO at the configured interval using `ADOIntegration.get_work_items(column)`.
3. Claim each returned work item.
4. Run the agent-specific placeholder task.
5. Send a Teams approval request or completion notification.
6. Wait for approval callback where applicable.
7. Move the work item to the next ADO column.

Each agent exposes `process_next_item()` for one-item execution. `run()` remains the long-running polling wrapper and drains available work items in the configured column each polling cycle.

`process_next_item()` emits structured lifecycle events, retries configured transient failures, and moves permanent failures to the configured error column when possible.

## Local Harness

The `harness/` package runs the workflow without Azure, Fabric, Purview, or Teams. It uses in-memory fake clients and the configured lifecycle to move a work item through every agent.

```bash
uv run python -m harness.run
```

The harness stores stage artifacts on the fake board so downstream agents consume the previous stage output. It also records emitted events for assertions.

## Shared Skills

The `shared_skills` modules are mounted into each container at `/app/shared_skills`.

- `ado_integration`: creates an Azure DevOps connection and provides placeholder methods for claim, query, detail lookup, move, and wiki update operations.
- `approval_server`: starts a lightweight stdlib HTTP callback server for `POST /approve/<work_item_id>` and tracks approved work items.
- `agent_runtime`: shared retry and failure-result helpers.
- `config`: loads runtime configuration from `CONFIG_PATH` or `config/default.json`.
- `contracts`: protocol definitions for board, notification, Fabric, governance, and approval clients.
- `events`: structured event constants and in-memory/null event recorders.
- `teams_integration`: posts MessageCard payloads to `TEAMS_WEBHOOK`.
- `fabric_integration`: wraps placeholder Microsoft Fabric workspace, pipeline, and dataflow operations.
- `purview_integration`: wraps placeholder Microsoft Purview source, scan, and metadata operations.

The skill loader deletes a previously loaded module from `sys.modules` before loading from disk, but agents only call `get_skill()` during initialization today. That means runtime hot reload is not yet fully wired into the polling loop.

## Runtime And Docker

`docker-compose.yml` defines one service per agent and mounts `./shared_skills:/app/shared_skills` and `./config:/app/config:ro`.

Run locally with:

```bash
docker-compose build
docker-compose up
```

The Dockerfiles install:

- `python:3.9-slim`
- Python packages: `rtk`, `adam`, `azure-devops`, `azure-identity`, `azure-mgmt-fabric`, `azure-purview-scanning`, `requests`, `pytest`
- System packages: `ca-certificates`

The Dockerfiles do not install Claude Code, Mistral Vibe, or Codex. If those CLIs are present in a derived image, `entrypoint.sh` can configure supported tools from environment variables; otherwise it skips them without failing the container.

The approval-gated agents start a lightweight callback server on their configured port. Teams approval cards post to `/approve/<work_item_id>`, and the agent waits for approval before moving the item forward.

## Configuration

Project defaults live in `config/default.json`. Use that file for board columns, agent ports, callback URL construction, polling intervals, approval timeouts, ADO/Fabric/Purview defaults, placeholder work item IDs, sample architecture output, semantic model output, pipeline names, QA results, and governance audit results.

Set `CONFIG_PATH` to load a different JSON config file. Environment variables still provide secrets and deployment-specific overrides:

## Environment Variables

Currently referenced by code or compose:

- `ADO_PAT`: Azure DevOps personal access token.
- `ADO_ORGANIZATION_URL`: optional override for configured ADO organization URL.
- `ADO_PROJECT_NAME`: optional override for configured ADO project name.
- `TEAMS_WEBHOOK`: Microsoft Teams incoming webhook URL.
- `AZURE_SUBSCRIPTION_ID`: used by `FabricIntegration`.
- `AZURE_RESOURCE_GROUP_NAME`: optional override for configured Azure resource group.
- `PURVIEW_ACCOUNT_NAME`: used by `PurviewIntegration`.
- `DATA_ARCHITECT_PORT`, `DATA_ENGINEER_PORT`, `QA_ENGINEER_PORT`, `DATA_ANALYST_PORT`, `DATA_STEWARD_PORT`: optional Docker host port overrides for local callback servers.
- `CLAUDE_API_KEY`: used to configure Claude Code.
- `MISTRAL_API_KEY`: used to configure Mistral Vibe.
- `CODEX_API_KEY`: used to configure Codex.

## Testing

Tests are written with `pytest` and use mocks for shared skills. Dependencies are managed with `uv`. Run:

```bash
uv sync --dev
uv run pytest tests/ -v
```

Individual test modules can also be run directly, for example:

```bash
python tests/test_data_architect.py
```

The current tests exercise agent methods directly and cover the stdlib approval callback server. They do not run infinite polling loops, Docker builds, live Azure clients, or real Teams webhook calls.

## Current Implementation Notes

- Much of the integration logic is still placeholder code. `ADOIntegration.get_work_items()` always returns simulated IDs.
- The agents import shared skills from `/app/shared_skills`, which works in containers. Local tests avoid this by mocking `SkillLoader`.
- Each agent writes logs to a local `*.log` file and to stdout.
- Approval callback handling lives in `shared_skills/approval_server` instead of per-agent `webhook.py` files.

## Development Guidance

- Keep changes scoped to the relevant agent and shared skill module.
- Prefer updating shared behavior in `shared_skills` rather than copying logic across all five agents.
- If changing the lifecycle, update the agent method, role `SKILLS.md`, tests, and this file together.
- Do not make live Azure, Fabric, Purview, or Teams calls from tests. Use mocks or fakes.
- Avoid changing Dockerfiles independently unless the same dependency or tool change is intentionally needed for only one agent.
- Put runtime values in `config/default.json` or an alternate config file loaded by `CONFIG_PATH`; keep secrets in environment variables.

## Useful Commands

```bash
uv sync --dev
uv run pytest tests/ -v
uv run python -m harness.run
docker-compose build
docker-compose up
docker-compose logs -f
```

`Makefile` targets are also available:

```bash
make test
make harness
make syntax
make compose-config
make docker-build
make docker-smoke
```

Docker targets require Docker Compose to be available in the current environment.

## Recommended Next Work

1. Replace placeholder ADO queries and moves with real WIQL and work item update operations.
2. Add focused tests for shared skill modules with mocked SDK clients.
3. Decide whether hot reload is required; if so, reload skills inside the polling cycle or add file-change detection.
