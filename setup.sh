#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALID_AGENTS=(
  data_architect
  data_engineer
  qa_engineer
  data_analyst
  data_steward
)

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

usage() {
  echo "Usage: $0 [agent_name]" >&2
  echo "Valid agents: ${VALID_AGENTS[*]}" >&2
  echo "Default agent: data_architect" >&2
}

is_valid_agent() {
  local requested_agent="$1"
  local valid_agent

  for valid_agent in "${VALID_AGENTS[@]}"; do
    if [ "$requested_agent" = "$valid_agent" ]; then
      return 0
    fi
  done

  return 1
}

require_command uv

if [ "$#" -gt 1 ]; then
  usage
  exit 2
fi

AGENT_NAME="${1:-data_architect}"
if ! is_valid_agent "$AGENT_NAME"; then
  echo "Unknown agent: $AGENT_NAME" >&2
  usage
  exit 2
fi

cd "$PROJECT_DIR"
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  . "$PROJECT_DIR/.env"
  set +a
fi
uv sync --dev

echo "Starting $AGENT_NAME in this terminal."
echo "Press Ctrl+C to stop the agent."

exec uv run python -m agents.runner "$AGENT_NAME"
