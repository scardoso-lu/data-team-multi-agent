# Multi-Agent Data Engineering Team

## Purpose
This repository contains a Python prototype of a multi-agent data engineering workflow. Six role-specific agents poll Azure DevOps (ADO) board columns, perform their lifecycle stage, write status updates and approval requests to the ADO ticket discussion, and move work items to the next configured column.

The intended lifecycle is defined in `config/default.json` under each agent's `column` and `next_column` values.

```text
Requirements -> Architecture -> Engineering -> QA -> Analytics -> Governance -> Done
```

## Current Repository Layout

```text
.
├── agents/
│   ├── requirements_analyst/
│   ├── data_architect/
│   ├── data_engineer/
│   ├── qa_engineer/
│   ├── data_analyst/
│   └── data_steward/
├── shared_skills/
│   ├── ado_integration/
│   ├── agent_base/
│   ├── approval_server/
│   ├── approvals/
│   ├── artifacts/
│   ├── artifact_types/
│   ├── checkpoint/
│   ├── code_executor/
│   ├── config/
│   ├── context/
│   ├── contracts/
│   ├── delegation/
│   ├── evaluation/
│   ├── events/
│   ├── feedback/
│   ├── llm_integration/
│   ├── mcp/
│   ├── memory/
│   ├── middleware/
│   ├── planning/
│   ├── policy/
│   ├── purview_integration/
│   ├── release_gates/
│   ├── replay/
│   ├── teams_integration/
│   ├── tools/
│   └── workspace/
├── tests/
├── config/
├── harness/
├── roadmap/
├── install.sh
├── setup.sh
├── Makefile
├── pyproject.toml
├── AGENTS.md
├── CLAUDE.md
├── LICENSE
└── README.md
```

Each role directory contains:

- `app.py`: the concrete agent class and long-running polling wrapper.
- `agent.md`: role-specific operating principles, production safety constraints, security boundaries, and best practices.
- `SKILLS.md`: role-specific skill documentation.

Shared startup, dependency construction, and prompt loading live outside the role directories:

- `agents/skill_loader.py`: dynamic loader for modules in `shared_skills`.
- `agents/task_loader.py`: loads agent LLM prompts from `agents/tasks.md`.
- `agents/tasks.md`: task prompt source, keyed by agent name.
- `agents/registry.py`: maps agent names to their concrete classes.
- `agents/runner.py`: runs one named agent.
- `install.sh`: installs local system and Python dependencies.
- `setup.sh`: starts one named agent in the current terminal session.

## Agents

| Agent | Main class | Config key | Board column |
| --- | --- | --- | --- |
| Requirements Analyst | `RequirementsAnalystAgent` | `requirements_analyst` | `Requirements` |
| Data Architect | `DataArchitectAgent` | `data_architect` | `Architecture` |
| Data Engineer | `DataEngineerAgent` | `data_engineer` | `Engineering` |
| QA Engineer | `QAEngineerAgent` | `qa_engineer` | `QA` |
| Data Analyst | `DataAnalystAgent` | `data_analyst` | `Analytics` |
| Data Steward | `DataStewardAgent` | `data_steward` | `Governance` |

All board-processing agents inherit the shared template in `shared_skills/agent_base`. Each role supplies only its stage-specific work, artifact type, validators, correction behavior, declared dependencies, and optional policy or governance hooks.

The Requirements Analyst validates and classifies incoming work before Architecture. Business work items must include at least 3 input and expected-output examples in `business_io_examples`. The only fallback is a human-confirmed exploration topic: if the work item explicitly includes a confirmation flag such as `human_confirmed_exploration`, `exploration_confirmed`, `Custom.ExplorationConfirmed`, or a tag such as `ExplorationConfirmed` or `is_exploration_topic`, the workflow may generate exploratory examples, mark the artifact as requiring human spec validation, and continue to approval. Without either business examples or explicit exploration confirmation, the Requirements Analyst blocks and asks for the missing examples.

The Data Architect consumes the validated requirements artifact. For parent work item types such as Epics and Features, it splits the specification into engineer-ready `user_stories` and creates linked technical child work items using the configured Azure DevOps process mapping, for example User Story for Agile or Issue for Basic. For leaf items such as an existing Issue, User Story, or Bug, it writes the flow specification to the current Azure DevOps item Description while preserving existing Description text below it. Each user story must contain the story text, a Mermaid `flowchart LR` implementation specification with step descriptions, checklist-style acceptance criteria, and applicable business or exploration examples. Acceptance criteria use `{"done": "", "item": "..."}` so Data Engineer can later mark completed items with `done: "X"`.

Data Engineer uses the user stories and examples as implementation targets. It only prepares a human-executable implementation package; Fabric workspace creation, pipeline deployment, dataflow execution, and permission changes are human-only privileged actions. QA Engineer uses the examples as acceptance-test targets. Data Analyst reviews the examples against semantic definitions before Governance. Data Steward performs the final governance and release-readiness review.

## Runtime Pattern

All agents follow the same broad pattern:

1. Load shared skills with `SkillLoader` when concrete clients are not injected.
2. Poll ADO at the configured interval using `ADOIntegration.get_work_items(column)`.
3. Claim the next returned work item.
4. Write a checkpoint under the configured checkpoint directory.
5. Load work item details.
6. Run the agent-specific task, usually through a local LLM CLI with deterministic fallback output.
7. Validate and, when supported, correct artifacts after validation errors.
8. Save the stage artifact back to the board client.
9. Emit structured lifecycle events.
10. Write ADO ticket discussion updates for approval requests, missing inputs, completion status, or failures.
11. Poll the approval store for a human decision where applicable.
12. Move the work item to the next ADO column, rework column, approval-timeout column, or error column.

Each agent exposes `process_next_item()` for one-item execution. `run()` remains the long-running polling wrapper and drains available work items in the configured column each polling cycle.

`process_next_item()` emits lifecycle events, retries configured transient failures, writes and clears checkpoints, and moves permanent failures to the configured error column when possible.

## Local Harness

The `harness/` package runs the workflow without Azure, Fabric, Purview, or external notification services. It uses in-memory fake clients and the configured lifecycle to move a work item through every agent.

```bash
uv run python -m harness.run
make harness
```

The harness starts in the Requirements column, stores stage artifacts on the fake board so downstream agents consume previous outputs, and records emitted events for assertions.

## Shared Skills

The `shared_skills` modules are loaded from the local repository by `agents/skill_loader.py`.

- `ado_integration`: creates an Azure DevOps connection and provides placeholder claim, query, detail lookup, move, child item, and wiki/update operations.
- `agent_base`: shared board-processing template, dependency factory, approval routing, checkpointing, tool registration, validation correction loop, and polling wrapper.
- `agent_runtime`: shared retry, blocked-work, and failure-result helpers.
- `approval_server`: in-memory approval store and polling behavior.
- `approvals`: approval record constants and constructors.
- `artifacts`: artifact validation and deterministic artifact-building helpers.
- `artifact_types`: typed artifact definitions.
- `checkpoint`: checkpoint write, clear, and stale checkpoint helpers.
- `code_executor`: sandboxed local Python and shell command execution tools.
- `config`: loads runtime configuration from `CONFIG_PATH` or `config/default.json`.
- `context`: context-window helpers.
- `contracts`: protocol definitions for board, notification, governance, and approval clients.
- `delegation`: in-process subagent dispatch and `delegate_task` tool.
- `events`: structured event constants plus null, memory, stdout, and file JSONL event sinks.
- `evaluation`: run scorecard helpers derived from event streams.
- `feedback`: utilities for storing human approval/rejection outcomes as JSONL.
- `llm_integration`: invokes local authenticated Codex, Claude Code, or Mistral CLIs and falls back to deterministic artifacts when no CLI is available.
- `mcp`: lightweight MCP client and tool-adapter primitives for registering external tool shapes.
- `memory`: persistent memory helpers.
- `middleware`: before/after agent hooks for context sizing, guardrails, memory, PII handling, and summarisation.
- `planning`: utility heuristics for ranking candidate plan steps plus in-agent todo tracking/tools.
- `policy`: lightweight policy rule engine for artifact governance checks.
- `purview_integration`: placeholder Microsoft Purview source, scan, and metadata operations.
- `release_gates`: readiness-gate evaluator for release decisions.
- `replay`: trace loading and comparison helpers for offline regression replay.
- `teams_integration`: legacy compatibility name for the notification client; writes approval requests and status updates to ADO work item history.
- `tools`: tool registry and board tools used by TAO-style LLM loops.
- `workspace`: per-agent/per-work-item local workspaces and file tools.

The skill loader deletes a previously loaded module from `sys.modules` before loading from disk, but agents only call `get_skill()` during initialization today. Runtime hot reload is therefore not fully wired into the polling loop.

## Local Runtime

Docker assets are not used. Local runtime is managed by `setup.sh`, which starts one named agent in the current terminal session.

Run one agent locally with:

```bash
./install.sh
./setup.sh
```

By default `setup.sh` starts `data_architect`. Pass another role name, such as `./setup.sh requirements_analyst` or `./setup.sh qa_engineer`, to run a different agent.

Run one agent directly with:

```bash
uv run python -m agents.runner requirements_analyst
```

Available agent names are:

```text
requirements_analyst
data_architect
data_engineer
qa_engineer
data_analyst
data_steward
```

Approval-gated agents create approval records, write the approval ID to the ADO ticket discussion, and poll the approval store until the record is approved, rejected, or timed out.

## Configuration

Project defaults live in `config/default.json`. Use that file for board columns, agent ports, polling intervals, approval timeouts, ADO/Fabric/Purview defaults, placeholder work item IDs, sample artifacts, event sinks, LLM provider order, policy settings, and release-gate defaults.

Set `CONFIG_PATH` to load a different JSON config file. Secrets and deployment-specific values must live in environment variables, not in JSON config files.

For local runtime, use `.env` based on `.env.example`. `.env` is gitignored and sourced by `setup.sh`; agent code consumes the resulting environment variables and must not read `.env` directly.

## Environment Variables

Currently referenced by code:

- `ADO_PAT`: Azure DevOps personal access token.
- `ADO_ORGANIZATION_URL`: Azure DevOps organization URL.
- `ADO_PROJECT_NAME`: Azure DevOps project name.
- `PURVIEW_ACCOUNT_NAME`: used by `PurviewIntegration`.
- `CONFIG_PATH`: optional path to a JSON config override.
- `SHARED_SKILLS_DIR`: optional override for shared skill module loading.

LLM API keys are not used by this repository. Agents invoke local authenticated CLIs through `shared_skills/llm_integration`; authenticate Codex, Claude Code, and Mistral Vibe with their own CLI login flows outside this app.

## Testing

Tests are written with `pytest` and use mocks or fakes for shared skills. Dependencies are managed with `uv`. Run:

```bash
uv sync --dev
uv run pytest tests/ -v
```

Individual test modules can also be run directly, for example:

```bash
uv run pytest tests/test_requirements_analyst.py -v
uv run pytest tests/test_data_architect.py -v
```

The tests exercise agent methods directly, the harness workflow, approval-store polling, shared skill helpers, and roadmap foundation modules. They do not run infinite polling loops or live Azure clients.

## Current Implementation Notes

- Much of the external integration logic is still placeholder code. Live Azure, Fabric, Purview, and notification behavior must be mocked or faked in tests.
- Sprint 8 is implemented. Requirements validation and classification now live in `RequirementsAnalystAgent`; `DataArchitectAgent` consumes a validated `RequirementsArtifact`, generates exploration examples only when the upstream artifact marks the item as exploration, and no longer repeats raw work-item classification.
- The agents import shared skills through `agents/skill_loader.py`, which prefers `SHARED_SKILLS_DIR` and then the repository `shared_skills` directory.
- Agent LLM prompts live in `agents/tasks.md`; keep task keys stable and avoid inline prompt strings in agent code.
- Each agent writes logs under `logs/<agent_name>/` and to stdout.
- Approval polling lives in `shared_skills/approval_server` instead of per-agent approval handlers.
- The local harness remains deterministic by injecting a fallback LLM client.
- The current worktree may contain unresolved Git index conflicts even when conflict markers are absent from file contents; check `git status --short` before running broad formatting or merge commands.

## Development Guidance

- Keep changes scoped to the relevant agent and shared skill module.
- Preserve and follow each role's `agent.md` constraints when changing agent behavior.
- Treat each role's `Core Knowledge And Hard Constraints` as mandatory guardrails: do not read secret files, commit to protected branches, create destructive data statements, remove files without approval, or perform live production-impacting actions without explicit human approval.
- Prefer updating shared behavior in `shared_skills` rather than copying logic across role agents.
- If changing the lifecycle, update the agent method, role `SKILLS.md`, role `agent.md` when constraints change, `agents/tasks.md`, tests, `config/default.json`, `README.md`, and this file together.
- Do not make live Azure, Fabric, Purview, or external notification calls from tests. Use mocks or fakes.
- Put non-sensitive runtime defaults in `config/default.json` or an alternate config file loaded by `CONFIG_PATH`; keep secrets, account names, organization URLs, project names, resource group names, and tokens in environment variables.
- When adding or changing artifact structure, update validators in `shared_skills/artifacts` and typed definitions in `shared_skills/artifact_types`.
- Keep local harness changes deterministic; avoid requiring LLM CLIs, cloud credentials, or network access for `make harness` and `make test`.

## Useful Commands

```bash
uv sync --dev
uv run pytest tests/ -v
uv run python -m harness.run
uv run python -m agents.runner requirements_analyst
./install.sh
./setup.sh data_architect
```

`Makefile` targets are also available:

```bash
make sync
make test
make harness
make syntax
make setup-check
make install-check
```

## Recommended Next Work

1. Replace placeholder ADO queries and moves with real WIQL and work item update operations.
2. Add focused tests for shared skill modules with mocked SDK clients.
3. Decide whether runtime hot reload is required; if so, reload skills inside the polling cycle or add file-change detection.
4. Continue roadmap implementation and reconciliation for sprints 9-14, especially where duplicate sprint numbers cover both governance features and harness primitives.
