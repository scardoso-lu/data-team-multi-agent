"""Local CLI LLM adapter.

Agents use this module instead of provider API keys. The adapter calls local,
already-authenticated CLIs and falls back to deterministic defaults when no CLI
is available, which keeps tests and the local harness offline-safe.
"""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMCommand:
    """Command template for one local LLM CLI invocation."""

    provider: str
    args: tuple[str, ...]


class LocalLLMClient:
    """Runs prompts through local Codex, Claude, or Mistral CLI tools."""

    DEFAULT_COMMANDS = (
        LLMCommand("codex", ("codex", "exec", "--skip-git-repo-check", "-")),
        LLMCommand("codex", ("codex", "exec", "-")),
        LLMCommand("claude", ("claude", "-p", "{prompt}")),
        LLMCommand("claude", ("claude-code", "-p", "{prompt}")),
        LLMCommand("mistral", ("mistral-vibe", "run", "--prompt", "{prompt}")),
        LLMCommand("mistral", ("mistral", "chat", "--message", "{prompt}")),
    )

    def __init__(self, config=None, commands=None, timeout_seconds=None):
        self.config = config
        self.commands = self._configured_commands(commands)
        configured_timeout = None
        if config is not None:
            configured_timeout = config.get("llm", "timeout_seconds", default=None)
        self.timeout_seconds = timeout_seconds or configured_timeout or 120

    def _configured_commands(self, commands):
        selected_commands = tuple(commands or self.DEFAULT_COMMANDS)
        if self.config is None or commands is not None:
            return selected_commands

        providers = self.config.get("llm", "providers", default=None)
        if not providers:
            return selected_commands

        allowed = set(providers)
        filtered = tuple(command for command in selected_commands if command.provider in allowed)
        return filtered or selected_commands

    def complete_text(self, task, payload, fallback=""):
        """Return model text, or fallback when all local CLIs are unavailable."""
        prompt = self._build_prompt(task, payload, response_format="text")
        result = self._run_first_available(prompt)
        return result if result is not None else fallback

    def complete_json(self, task, payload, fallback=None):
        """Return parsed JSON from a local CLI response, or fallback."""
        prompt = self._build_prompt(task, payload, response_format="json")
        result = self._run_first_available(prompt)
        if not result:
            return fallback

        parsed = extract_json(result)
        if parsed is None:
            logger.warning("Local LLM returned non-JSON output for task %s", task)
            return fallback
        return parsed

    def _build_prompt(self, task, payload, response_format):
        payload_text = json.dumps(payload, indent=2, sort_keys=True)
        if response_format == "json":
            instruction = "Return only valid JSON. Do not include markdown fences."
        else:
            instruction = "Return concise plain text."

        return (
            f"Task:\n{task}\n\n"
            f"Input JSON:\n{payload_text}\n\n"
            f"Constraints:\n{instruction}\n"
            "Do not request or expose secrets. Do not suggest destructive data changes."
        )

    def _run_first_available(self, prompt):
        for command in self.commands:
            executable = command.args[0]
            if shutil.which(executable) is None:
                continue

            args, stdin = self._render_command(command.args, prompt)
            try:
                completed = subprocess.run(
                    args,
                    input=stdin,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Local LLM provider %s failed: %s", command.provider, exc)
                continue

            if completed.returncode == 0 and completed.stdout.strip():
                return completed.stdout.strip()

            stderr = completed.stderr.strip()
            logger.warning(
                "Local LLM provider %s exited with %s: %s",
                command.provider,
                completed.returncode,
                stderr[:500],
            )

        return None

    def _render_command(self, args, prompt):
        rendered = []
        prompt_was_argument = False
        for arg in args:
            if arg == "{prompt}":
                rendered.append(prompt)
                prompt_was_argument = True
            else:
                rendered.append(arg)

        stdin = None if prompt_was_argument else prompt
        return rendered, stdin


def extract_json(text):
    """Parse direct JSON or the first JSON object/array embedded in text."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        return value
    return None
