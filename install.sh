#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/.uv-cache}"
INSTALL_AI_TOOLS="${INSTALL_AI_TOOLS:-1}"

has_command() {
  command -v "$1" >/dev/null 2>&1
}

install_apt_packages() {
  if ! has_command apt-get; then
    return 1
  fi

  local sudo_cmd=""
  if [ "$(id -u)" -ne 0 ]; then
    if ! has_command sudo; then
      echo "sudo is required to install system packages with apt-get." >&2
      exit 1
    fi
    sudo_cmd="sudo"
  fi

  $sudo_cmd apt-get update
  $sudo_cmd apt-get install -y \
    ca-certificates \
    curl \
    python3 \
    python3-venv
}

install_uv() {
  if has_command uv; then
    return
  fi

  if has_command brew; then
    brew install uv
    return
  fi

  if has_command pipx; then
    pipx install uv
    return
  fi

  if has_command python3; then
    python3 -m pip install --user uv
    return
  fi

  echo "Python 3 is required to install uv." >&2
  exit 1
}

install_brew_cli() {
  local command_name="$1"
  local formula_name="$2"

  if has_command "$command_name"; then
    return
  fi

  if ! has_command brew; then
    echo "Homebrew is required to install $command_name automatically." >&2
    return
  fi

  brew install "$formula_name"
}

install_ai_tools() {
  if [ "$INSTALL_AI_TOOLS" != "1" ]; then
    echo "Skipping AI CLI installation because INSTALL_AI_TOOLS=$INSTALL_AI_TOOLS."
    return
  fi

  install_brew_cli codex codex
  install_brew_cli claude claude-code
  install_brew_cli mistral-vibe mistral-vibe
}

if ! install_apt_packages; then
  echo "apt-get not found. Install these system packages manually if needed: ca-certificates curl python3 python3-venv"
fi

install_uv
install_ai_tools

cd "$PROJECT_DIR"
uv --cache-dir "$UV_CACHE_DIR" sync --dev

if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$PROJECT_DIR/.env.example" ]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  echo "Created .env from .env.example. Fill in local values before running live integrations."
fi

echo "Install complete."
echo "Run agents with: ./setup.sh"
