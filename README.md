# data-team-multi-agent

Python prototype for a modular multi-agent data engineering workflow.

## Run Agents Locally

Install local dependencies first:

```bash
./install.sh
```

The installer installs Python dependencies plus the local CLIs used by this prototype: Codex, Claude Code, Mistral Vibe, and `uv`. AI CLIs are installed with Homebrew. Set `INSTALL_AI_TOOLS=0 ./install.sh` to skip AI CLI installation.

Create local environment settings in `.env`; use `.env.example` as the template. The file is gitignored and is sourced by `setup.sh`. Do not put secrets, organization URLs, project names, account names, or resource group names in `config/default.json`.

The agents invoke LLMs through local authenticated CLIs, not provider API keys. Authenticate Codex, Claude Code, and Mistral Vibe with their own CLI login flows before starting the agents. If no local LLM CLI is available, the workflow falls back to deterministic configured artifacts so tests and the harness remain offline-safe.

Start one agent in the current terminal session:

```bash
./setup.sh
```

By default this starts `data_architect`. Pass a role name to start a different agent, for example `./setup.sh qa_engineer`.

- `data_architect`
- `data_engineer`
- `qa_engineer`
- `data_analyst`
- `data_steward`

Press `Ctrl+C` to stop the agent. You can also run one agent directly:

```bash
uv run python -m agents.runner data_architect
```

## Tests

```bash
uv run pytest tests/ -v
```
