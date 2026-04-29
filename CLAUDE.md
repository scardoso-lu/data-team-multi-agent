# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
./install.sh          # installs uv + Python deps + optional AI CLIs (Codex, Claude, Mistral)
uv sync --dev         # just sync Python deps

# Run agents
./setup.sh                        # starts data_architect (default)
./setup.sh qa_engineer            # starts a specific agent
uv run python -m agents.runner data_architect  # run directly

# Run the local harness (no Azure required, fully in-memory)
uv run python -m harness.run
make harness

# Tests
uv run pytest tests/ -v           # all tests
uv run pytest tests/test_data_architect.py -v  # single module
python tests/test_data_architect.py            # run directly

# Syntax check and Makefile shorthands
make syntax        # AST-parse all .py files
make test
make setup-check
make install-check
```

## Architecture

### Pipeline

Work items flow through five ADO board columns in sequence:

```
Architecture → Engineering → QA → Analytics → Governance → Done
```

Each column is owned by one agent. Agents poll for work items in their column, execute stage work, request human approval (via ADO ticket discussion), then move approved items to the next column. Rejected items go to `Rework`; timed-out approvals go to `Approval Timeout`; hard failures go to `Error`.

### Agent Structure

All five agents (`DataArchitectAgent`, `DataEngineerAgent`, `QAEngineerAgent`, `DataAnalystAgent`, `DataStewardAgent`) extend `BoardAgent` from `shared_skills/agent_base`. The only thing each concrete agent implements is:

- `agent_key` / `dependency_names` / `artifact_type` class attributes
- `execute_stage(stage_input)` — the stage-specific work, must return an artifact dict
- `validate_artifact(artifact)` — delegates to the appropriate `validate_*` function in `shared_skills/artifacts`

`BoardAgent.process_next_item()` is the single-item entry point used by tests and the harness. `BoardAgent.run()` wraps it in an infinite polling loop.

### Shared Skills Loading

`agents/skill_loader.py` loads modules from `shared_skills/` at runtime using `importlib`. Agents call `SkillLoader().get_skill(name)` to get the module, then instantiate clients from it (e.g. `ADOIntegration`, `TeamsIntegration`). `DependencyProvider` in `agent_base` wraps this factory pattern.

The `shared_skills/` modules are also on `sys.path` via `pyproject.toml` (`pythonpath = [".", "shared_skills"]`), so tests and agents can `import` them directly without going through the skill loader.

### Key shared_skills modules

| Module | Purpose |
|---|---|
| `agent_base` | `BoardAgent`, `DependencyProvider`, `AgentRuntimeMixin`, `configure_agent_logger` |
| `agent_runtime` | `WorkItemBlocked`, `retry_operation`, `failure_result` |
| `artifacts` | All artifact validators and builders (`validate_architecture_artifact`, `validate_fabric_artifact`, etc.) |
| `approvals` | `InMemoryApprovalStore`, approval record helpers, status constants (`APPROVED`, `REJECTED`, `TIMED_OUT`) |
| `approval_server` | `ApprovalServer` — HTTP server and client that agents use for approval polling |
| `events` | Event constants, `EventRecorder` (in-memory), `NullEventRecorder`, `StdoutJsonEventSink`, `FileJsonEventSink` |
| `contracts` | `Protocol` definitions for `BoardClient`, `NotificationClient`, `GovernanceClient`, `ApprovalClient` |
| `llm_integration` | `LocalLLMClient` — tries Codex, Claude, Mistral CLIs in order; falls back to `fallback=` when no CLI is available |
| `config` | `AppConfig` — loads `config/default.json` or `CONFIG_PATH` env var |
| `teams_integration` | `TeamsIntegration` — writes to ADO ticket discussion (not MS Teams) |
| `ado_integration` | `ADOIntegration` — Azure DevOps board operations (still largely placeholder) |
| `purview_integration` | `PurviewIntegration` — Microsoft Purview metadata operations |

### LLM Integration

`LocalLLMClient.complete_json(task, payload, fallback)` tries each available local CLI (Codex, Mistral, Claude) and parses JSON from the response. If no CLI is available or the response is non-JSON, it returns `fallback`. This is how the entire system stays offline-safe for tests and the harness — always pass a sensible `fallback`.

### Artifact Contracts

Each agent stage produces a typed artifact dict validated in `shared_skills/artifacts`:

- **Architecture** (`validate_architecture_artifact`): requires `tables`, `relationships`, `business_io_examples`, `user_stories`
- **Fabric/Engineering** (`validate_fabric_artifact`): requires `execution_mode="human_required"`, `proposed_workspace`, `pipelines`, `business_io_examples`, `user_stories`
- **Quality/QA** (`validate_quality_artifact`): requires pipeline-keyed `checks` with `status` and `issues`
- **Semantic model** (`validate_semantic_model_artifact`): requires `tables`, `relationships`, `business_io_examples`
- **Governance** (`validate_governance_artifact`): requires all five lifecycle section keys

`business_io_examples` must be a list of at least 3 dicts each with `input` and `expected_output`. The Data Architect blocks with `WorkItemBlocked` if examples are missing and the item is not tagged as a human-confirmed exploration topic.

User story `acceptance_criteria` items use `{"done": "", "item": "..."}` format — `done` is either `""` (incomplete) or `"X"` (done). `validate_user_stories` enforces this.

### Testing

Tests use concrete fake clients from `harness/fakes.py` (`FakeBoardClient`, `FakeNotificationClient`, `FakeApprovalClient`, `FakeGovernanceClient`) rather than `unittest.mock`. Inject them directly into agent constructors:

```python
agent = DataArchitectAgent(ado=board, teams=teams, approvals=approvals, config=config, events=events)
result = agent.process_next_item()
```

Never use live Azure, Fabric, Purview, or notification clients in tests. `conftest.py` adds repo root and `shared_skills/` to `sys.path`.

### Configuration

- Non-sensitive defaults: `config/default.json` (board columns, poll intervals, approval timeouts, sample artifacts)
- Secrets and deployment-specific values: environment variables only (see `.env.example`)
- Override config file path: `CONFIG_PATH` env var
- `.env` is sourced by `setup.sh`; agent code must not read `.env` directly

### Development Rules

- Scope changes to the relevant agent and shared skill. Prefer updating `shared_skills` over copying logic across agents.
- Treat `agents/<role>/agent.md` constraints as mandatory hard guardrails for each role.
- If changing the lifecycle (columns, artifact shape, approval flow), update the agent method, `SKILLS.md`, `agent.md`, tests, and `AGENTS.md` together.
- Data Engineer only produces a human-executable implementation package; Fabric workspace creation, pipeline deployment, and permission changes are human-only privileged actions — enforce `execution_mode: "human_required"` in the fabric artifact.
- Debug artifacts for `data_architect` are written to `logs/data_architect/latest_specs.json` and `logs/data_architect/latest_work_item.json`.
- Sensitive keys (`secret`, `token`, `password`, `credential`, `authorization`, `pat`, `key`) are redacted before writing debug work item logs.
