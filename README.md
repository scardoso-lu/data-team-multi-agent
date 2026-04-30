# data-team-multi-agent

Python prototype for a modular multi-agent data engineering workflow. Six role-specific agents poll Azure DevOps board columns, execute their lifecycle stage, request human approval where required, and move work items through the pipeline.

```text
Requirements -> Architecture -> Engineering -> QA -> Analytics -> Governance -> Done
```

The project is still a local-first prototype: cloud integrations are represented by adapters and placeholders, while tests and the harness run with fakes and deterministic fallback artifacts.

## Quick Start

```bash
./install.sh
cp .env.example .env
./setup.sh
```

Fill `.env` with deployment-specific values such as `ADO_PAT`, `ADO_ORGANIZATION_URL`, and `ADO_PROJECT_NAME`. `.env` is sourced by `setup.sh` and must not be read directly by agent code.

By default `setup.sh` starts `data_architect`. Start a specific agent with:

```bash
./setup.sh requirements_analyst
./setup.sh qa_engineer
```

## Agents

| Agent | CLI name | Column | Next column |
| --- | --- | --- | --- |
| Requirements Analyst | `requirements_analyst` | Requirements | Architecture |
| Data Architect | `data_architect` | Architecture | Engineering |
| Data Engineer | `data_engineer` | Engineering | QA |
| QA Engineer | `qa_engineer` | QA | Analytics |
| Data Analyst | `data_analyst` | Analytics | Governance |
| Data Steward | `data_steward` | Governance | Done |

Run one agent directly:

```bash
uv run python -m agents.runner requirements_analyst
```

The agents invoke LLMs through local authenticated CLIs, currently Codex, Claude Code, and Mistral Vibe by default. No LLM API keys are used by this repository. When no CLI is available, the workflow falls back to deterministic configured artifacts so tests and the local harness stay offline-safe.

## Local Harness

Run the full six-stage pipeline in memory using fake board, notification, approval, governance, and LLM clients:

```bash
uv run python -m harness.run
make harness
```

The harness starts from the Requirements column, stores stage artifacts on the fake board, and records lifecycle events for assertions.

## Tests

```bash
uv sync --dev
uv run pytest tests/ -v
uv run pytest tests/test_requirements_analyst.py -v
make test
make syntax
```

Tests use mocks and fakes. They should not make live Azure, Fabric, Purview, LLM, or external notification calls.

## LLM Task Prompts

All prompts sent to the LLM are defined in [`agents/tasks.md`](agents/tasks.md), one `##` section per agent. Edit that file to change what an agent asks the model; do not inline prompt strings in agent code.

## Configuration

| What | Where |
| --- | --- |
| Non-sensitive defaults, columns, timeouts, sample artifacts, event sinks, LLM provider order | `config/default.json` |
| Secrets and deployment-specific values | environment variables sourced from `.env` |
| Override config file | `CONFIG_PATH` |
| Override shared skill directory | `SHARED_SKILLS_DIR` |

Key environment variables are `ADO_PAT`, `ADO_ORGANIZATION_URL`, `ADO_PROJECT_NAME`, and `PURVIEW_ACCOUNT_NAME`.

## Shared Runtime Features

- `shared_skills/agent_base`: common board-processing template, approval routing, checkpointing, retries, artifact validation, correction attempts, policy checks, and event emission.
- `shared_skills/approval_server` and `shared_skills/approvals`: approval records and decision polling.
- `shared_skills/artifacts` and `shared_skills/artifact_types`: artifact builders, validators, and typed artifact definitions.
- `shared_skills/events`: null, memory, stdout JSONL, and file JSONL event sinks.
- `shared_skills/llm_integration`: local CLI provider invocation with deterministic fallback behavior.
- `shared_skills/middleware`: optional before/after hooks for context sizing, guardrails, memory, PII handling, and summarisation.
- `shared_skills/tools`: tool registry and board tools used by TAO-style loops.
- `shared_skills/policy`, `replay`, `evaluation`, `feedback`, `planning`, and `release_gates`: roadmap foundation modules for governance, offline replay, scorecards, reviewer feedback, planning heuristics, and release readiness.

## Business Examples Requirement

Work items must include at least 3 input and expected-output examples in `business_io_examples`. The fallback path is an explicitly human-confirmed exploration topic, using a confirmation field such as `human_confirmed_exploration`, `exploration_confirmed`, `Custom.ExplorationConfirmed`, or a tag such as `ExplorationConfirmed` or `is_exploration_topic`.

Without business examples or explicit exploration confirmation, the Requirements Analyst blocks the item and asks for the missing examples.

## Roadmap

Planned and partially implemented improvements are tracked in [`roadmap/`](roadmap/). The current roadmap spans fourteen numbered sprints, with two overlapping sprint waves:

- Sprints 1-8 cover feedback loops, middleware, observability, checkpointing and typed state, memory, context management, TAO loop tools, and the Requirements Analyst/task refinement work.
- Sprints 9-14 cover both governance-oriented modules and harness primitives such as filesystem workspace, code execution, delegation, in-agent task planning, MCP integration, provider registry, and release readiness.

See [`roadmap/README.md`](roadmap/README.md) for the execution order and dependency map.

## Development Notes

- Keep lifecycle changes synchronized across agent code, `agents/tasks.md`, `config/default.json`, tests, `README.md`, and `AGENTS.md`.
- Prefer shared behavior in `shared_skills` over copying logic across agents.
- Keep tests and the harness deterministic and offline-safe.
- Check `git status --short` before broad edits. The current project state can include unresolved Git index conflicts even when working-tree files no longer contain conflict markers.
