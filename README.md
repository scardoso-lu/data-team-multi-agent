# data-team-multi-agent

Python prototype for a modular multi-agent data engineering workflow. Five role-specific
agents poll Azure DevOps board columns, execute their lifecycle stage, request human
approval, and move work items through the pipeline.

```
Architecture → Engineering → QA → Analytics → Governance → Done
```

## Quick Start

```bash
./install.sh          # install uv, Python deps, optional AI CLIs
cp .env.example .env  # fill in ADO_PAT, ADO_ORGANIZATION_URL, ADO_PROJECT_NAME
./setup.sh            # start data_architect (default)
./setup.sh qa_engineer  # or start a specific agent
```

The agents invoke LLMs through local authenticated CLIs (Codex, Claude Code, Mistral
Vibe) — no API keys needed. When no CLI is available the workflow falls back to
deterministic configured artifacts so tests and the local harness stay offline-safe.

## Run a Single Agent

```bash
uv run python -m agents.runner data_architect
```

Available agent names: `data_architect`, `data_engineer`, `qa_engineer`,
`data_analyst`, `data_steward`.

## Local Harness (no Azure required)

Runs the full five-stage pipeline in memory using fake clients:

```bash
uv run python -m harness.run
make harness
```

## Tests

```bash
uv run pytest tests/ -v                          # all tests
uv run pytest tests/test_data_architect.py -v   # single module
make test
make syntax   # AST-parse all .py files
```

## LLM Task Prompts

All prompts sent to the LLM are defined in [`agents/tasks.md`](agents/tasks.md),
one `##` section per agent. Edit that file to change what an agent asks the model —
do not inline prompt strings in agent code.

## Improvement Roadmap

Seven sprints of planned improvements are tracked in [`roadmap/`](roadmap/):

| Sprint | Topic |
|--------|-------|
| [1](roadmap/sprint-01-feedback-loop.md) | Self-correcting feedback loop |
| [2](roadmap/sprint-02-middleware-hooks.md) | Middleware hook system |
| [3](roadmap/sprint-03-observability.md) | LLM observability |
| [4](roadmap/sprint-04-checkpointing-typed-state.md) | Checkpointing & typed state |
| [5](roadmap/sprint-05-persistent-memory.md) | Persistent cross-session memory |
| [6](roadmap/sprint-06-context-management.md) | Context management & summarisation |
| [7](roadmap/sprint-07-tao-loop-tools.md) | TAO loop & tool calling |

See [`roadmap/README.md`](roadmap/README.md) for the execution order and dependency map.

## Configuration

| What | Where |
|------|-------|
| Non-sensitive defaults (columns, timeouts, sample artifacts) | `config/default.json` |
| Secrets and deployment-specific values | environment variables (`.env`) |
| Override config file | `CONFIG_PATH` env var |

Key environment variables: `ADO_PAT`, `ADO_ORGANIZATION_URL`, `ADO_PROJECT_NAME`,
`PURVIEW_ACCOUNT_NAME`.
