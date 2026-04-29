# Multi-Agent Data Engineering Team

## Purpose
This repository contains a Python prototype of a multi-agent data engineering workflow. Five role-specific agents poll Azure DevOps (ADO) board columns, perform placeholder work for their lifecycle stage, write status updates and approval requests to the ADO ticket discussion, and move work items to the next column.

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
│   ├── purview_integration/
│   └── teams_integration/
├── tests/
├── config/
├── harness/
├── setup.sh
├── pyproject.toml
├── AGENTS.md
├── LICENSE
└── README.md
```

Each agent directory currently contains:

- `app.py`: the agent class and infinite polling loop.
- `agent.md`: role-specific operating principles, production safety constraints, security boundaries, and best practices.
- `SKILLS.md`: role-specific skill documentation.

Shared startup and dependency construction now live outside the role directories:

- `agents/skill_loader.py`: dynamic loader for modules in `shared_skills`.
- `agents/registry.py`: maps agent names to their concrete classes.
- `agents/runner.py`: runs one named agent.
- `install.sh`: installs local system and Python dependencies.
- `setup.sh`: starts one named agent in the current terminal session.

## Agents

| Agent | Main class | Config key |
| --- | --- | --- |
| Data Architect | `DataArchitectAgent` | `data_architect` |
| Data Engineer | `DataEngineerAgent` | `data_engineer` |
| QA Engineer | `QAEngineerAgent` | `qa_engineer` |
| Data Analyst | `DataAnalystAgent` | `data_analyst` |
| Data Steward | `DataStewardAgent` | `data_steward` |

All agents inherit the shared board-processing template in `shared_skills/agent_base`. Each role supplies only its stage-specific work, artifact type, validators, and declared dependencies.

Business work items must include at least 3 input and expected-output examples in `business_io_examples`. The only fallback is a human-confirmed exploration topic: if the work item explicitly includes a confirmation flag such as `human_confirmed_exploration`, `exploration_confirmed`, `Custom.ExplorationConfirmed`, or a tag such as `ExplorationConfirmed` or `is_exploration_topic`, the Data Architect may generate exploratory examples, mark the artifact as requiring human spec validation, and continue to approval. Without either business examples or that explicit exploration confirmation, the Data Architect blocks and asks for the missing examples. The Data Architect pulls any work item type from Architecture. For Epics and Features, it splits the specification into engineer-ready `user_stories` and creates linked technical child work items using the configured Azure DevOps process mapping, for example User Story for Agile or Issue for Basic. For leaf items such as an existing Issue, User Story, or Bug, it writes the flow specification to the top of the current Azure DevOps item Description and preserves any existing Description text below it. Each user story must contain the story text, a Mermaid `flowchart LR` implementation specification with step descriptions, checklist-style acceptance criteria, and applicable business examples or exploration examples. Acceptance criteria use `{"done": "", "item": "..."}` so Data Engineer can later mark completed items with `done: "X"`. Data Engineer uses those user stories plus the examples as implementation targets. QA Engineer uses the examples as acceptance-test targets. Data Engineer only prepares a human-executable implementation package; Fabric workspace creation, pipeline deployment, dataflow execution, and permission changes are human-only privileged actions. Data Analyst reviews the examples against semantic definitions before Governance.

All agents follow the same broad pattern:

1. Load shared skills with `SkillLoader`.
2. Poll ADO at the configured interval using `ADOIntegration.get_work_items(column)`.
3. Claim each returned work item.
4. Run the agent-specific placeholder task.
5. Write an ADO ticket discussion update for approval requests, missing inputs, or completion status.
6. Poll the approval store for a human decision where applicable.
7. Move the work item to the next ADO column.

Each agent exposes `process_next_item()` for one-item execution. `run()` remains the long-running polling wrapper and drains available work items in the configured column each polling cycle.

`process_next_item()` emits structured lifecycle events, retries configured transient failures, and moves permanent failures to the configured error column when possible.

## Local Harness

The `harness/` package runs the workflow without Azure, Fabric, Purview, or external notification services. It uses in-memory fake clients and the configured lifecycle to move a work item through every agent.

```bash
uv run python -m harness.run
```

The harness stores stage artifacts on the fake board so downstream agents consume the previous stage output. It also records emitted events for assertions.

## Shared Skills

The `shared_skills` modules are loaded from the local repository by `agents/skill_loader.py`.

- `ado_integration`: creates an Azure DevOps connection and provides placeholder methods for claim, query, detail lookup, move, and wiki update operations.
- `approval_server`: stores approval records and lets agents poll for approved, rejected, or timed-out decisions.
- `agent_runtime`: shared retry and failure-result helpers.
- `config`: loads runtime configuration from `CONFIG_PATH` or `config/default.json`.
- `contracts`: protocol definitions for board, notification, governance, and approval clients.
- `events`: structured event constants and in-memory/null event recorders.
- `teams_integration`: legacy compatibility name for the notification client; writes approval requests and status updates to ADO work item history.
- `purview_integration`: wraps placeholder Microsoft Purview source, scan, and metadata operations.
- `llm_integration`: invokes local authenticated Codex, Claude Code, or Mistral CLIs and falls back to deterministic artifacts when no CLI is available.

The skill loader deletes a previously loaded module from `sys.modules` before loading from disk, but agents only call `get_skill()` during initialization today. That means runtime hot reload is not yet fully wired into the polling loop.

## Local Runtime

Docker assets were removed. Local runtime is managed by `setup.sh`, which starts one named agent in the current terminal session.

Run one agent locally with:

```bash
./install.sh
./setup.sh
```

By default `setup.sh` starts `data_architect`. Pass another role name, such as `./setup.sh qa_engineer`, to run a different agent.

Run one agent directly with:

```bash
uv run python -m agents.runner data_architect
```

Approval-gated agents create approval records, write the approval ID to the ADO ticket discussion, and poll the approval store until the record is approved, rejected, or timed out.

## Configuration

Project defaults live in `config/default.json`. Use that file for board columns, agent ports, polling intervals, approval timeouts, ADO/Fabric/Purview defaults, placeholder work item IDs, sample architecture output, semantic model output, pipeline names, QA results, and governance audit results.

Set `CONFIG_PATH` to load a different JSON config file. Secrets and deployment-specific values must live in environment variables, not in JSON config files.

For local runtime, use `.env` based on `.env.example`. `.env` is gitignored and sourced by `setup.sh`; agent code consumes the resulting environment variables and must not read `.env` directly.

## Environment Variables

Currently referenced by code:

- `ADO_PAT`: Azure DevOps personal access token.
- `ADO_ORGANIZATION_URL`: Azure DevOps organization URL.
- `ADO_PROJECT_NAME`: Azure DevOps project name.
- `PURVIEW_ACCOUNT_NAME`: used by `PurviewIntegration`.

LLM API keys are not used by this repository. Agents invoke local authenticated CLIs through `shared_skills/llm_integration`; authenticate Codex, Claude Code, and Mistral Vibe with their own CLI login flows outside this app.

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

The current tests exercise agent methods directly and cover approval-store polling. They do not run infinite polling loops or live Azure clients.

## Current Implementation Notes

- Much of the integration logic is still placeholder code. `ADOIntegration.get_work_items()` always returns simulated IDs.
- The agents import shared skills through `agents/skill_loader.py`, which prefers `SHARED_SKILLS_DIR` and then the repository `shared_skills` directory.
- Each agent writes logs to a local `*.log` file and to stdout.
- Approval polling lives in `shared_skills/approval_server` instead of per-agent approval handlers.

## Development Guidance

- Keep changes scoped to the relevant agent and shared skill module.
- Preserve and follow each role's `agent.md` constraints when changing agent behavior.
- Treat each role's `Core Knowledge And Hard Constraints` as mandatory guardrails: do not read secret files, commit to protected branches, create destructive data statements, remove files without approval, or perform live production-impacting actions without explicit human approval.
- Prefer updating shared behavior in `shared_skills` rather than copying logic across all five agents.
- If changing the lifecycle, update the agent method, role `SKILLS.md`, role `agent.md` when constraints change, tests, and this file together.
- Do not make live Azure, Fabric, Purview, or external notification calls from tests. Use mocks or fakes.
- Put non-sensitive runtime defaults in `config/default.json` or an alternate config file loaded by `CONFIG_PATH`; keep secrets, account names, organization URLs, project names, resource group names, and tokens in environment variables.

## Useful Commands

```bash
uv sync --dev
uv run pytest tests/ -v
uv run python -m harness.run
./install.sh
./setup.sh data_architect
```

`Makefile` targets are also available:

```bash
make test
make harness
make syntax
make setup-check
```

## Recommended Next Work

1. Replace placeholder ADO queries and moves with real WIQL and work item update operations.
2. Add focused tests for shared skill modules with mocked SDK clients.
3. Decide whether hot reload is required; if so, reload skills inside the polling cycle or add file-change detection.
