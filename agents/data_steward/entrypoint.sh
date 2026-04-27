#!/bin/sh
set -eu

configure_tool() {
    tool_name="$1"
    env_name="$2"

    eval "api_key=\${$env_name:-}"
    if [ -z "$api_key" ]; then
        return 0
    fi

    if [ "$tool_name" = "codex" ]; then
        echo "Skipping codex configuration: CODEX_API_KEY is provided through the environment."
        return 0
    fi

    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "Skipping $tool_name configuration: command not installed."
        return 0
    fi

    if ! "$tool_name" configure --help >/dev/null 2>&1; then
        echo "Skipping $tool_name configuration: configure command not supported."
        return 0
    fi

    echo "Configuring $tool_name..."
    "$tool_name" configure "--api-key=$api_key" || echo "Warning: $tool_name configuration failed; continuing."
}

configure_tool claude-code CLAUDE_API_KEY
configure_tool mistral-vibe MISTRAL_API_KEY
configure_tool codex CODEX_API_KEY

exec "$@"
