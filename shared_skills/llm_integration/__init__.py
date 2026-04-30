"""Local CLI LLM adapter.

Agents use this module instead of provider API keys. The adapter calls local,
already-authenticated CLIs and falls back to deterministic defaults when no CLI
is available, which keeps tests and the local harness offline-safe.
"""

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from events import LLM_CALL_COMPLETED, LLM_CALL_FAILED, LLM_CALL_STARTED
from llm_integration.builtin_providers import default_providers
from llm_integration.provider_registry import ProviderRegistry

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

    def __init__(self, config=None, commands=None, timeout_seconds=None, events=None, agent=None, middlewares=None):
        self.config = config
        self.commands = self._configured_commands(commands)
        configured_timeout = None
        if config is not None:
            configured_timeout = config.get("llm", "timeout_seconds", default=None)
        self.timeout_seconds = timeout_seconds or configured_timeout or 120
        self.events = events
        self.agent = agent or "unknown"
        self._last_provider = None
        self.middlewares = list(middlewares or [])

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

    def _configured_providers(self):
        if self.config is None:
            names = None
        else:
            per_agent = self.config.get("llm", "per_agent", default={}) or {}
            names = per_agent.get(self.agent)
            if names is None:
                names = self.config.get("llm", "providers", default=None)
        return ProviderRegistry(default_providers()).ordered(names)

    def complete_text(self, task, payload, fallback=""):
        """Return model text, or fallback when all local CLIs are unavailable."""
        prompt = self._build_prompt(task, payload, response_format="text")
        result = self._run_first_available(prompt)
        return result if result is not None else fallback

    def complete_json(self, task, payload, fallback=None):
        """Return parsed JSON from a local CLI response, or fallback."""
        start = time.monotonic()
        if self.events:
            self.events.emit(LLM_CALL_STARTED, self.agent, task=task[:120])
        context = {"task": task, "payload": payload, "agent": self.agent}
        prompt = self._build_prompt(task, payload, response_format="json")
        for middleware in self.middlewares:
            prompt = middleware.before_model(prompt, context)
        result = self._run_first_available(prompt)
        for middleware in reversed(self.middlewares):
            result = middleware.after_model(result, context)
        if not result:
            self._emit_completion(task, start, True)
            return fallback

        parsed = extract_json(result)
        if parsed is None:
            logger.warning("Local LLM returned non-JSON output for task %s", task)
            self._emit_completion(task, start, True)
            return fallback
        self._emit_completion(task, start, False)
        return parsed

    def _emit_completion(self, task, start_time, fallback_used):
        if self.events:
            self.events.emit(
                LLM_CALL_COMPLETED,
                self.agent,
                task=task[:120],
                latency_ms=int((time.monotonic() - start_time) * 1000),
                fallback_used=fallback_used,
                provider=self._last_provider,
            )

    def complete_json_with_correction(
        self, task, payload, fallback=None, previous_response=None, error=None
    ):
        if previous_response is not None and error is not None:
            correction_payload = {
                "original_payload": payload,
                "previous_response": previous_response,
                "validation_error": str(error),
                "instruction": (
                    "Your previous response failed validation. "
                    "Fix only the fields described in validation_error. "
                    "Return the complete corrected JSON."
                ),
            }
            return self.complete_json(task, correction_payload, fallback=fallback)
        return self.complete_json(task, payload, fallback=fallback)

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
        for provider in self._configured_providers():
            try:
                result = provider.complete(prompt, self.timeout_seconds)
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Local LLM provider %s failed: %s", provider.name, exc)
                continue
            if result:
                self._last_provider = provider.name
                return result

        if self.config is not None:
            return None

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
                self._last_provider = command.provider
                return completed.stdout.strip()

            stderr = completed.stderr.strip()
            logger.warning(
                "Local LLM provider %s exited with %s: %s",
                command.provider,
                completed.returncode,
                stderr[:500],
            )

        return None

    def run_tao_loop(self, task, payload, tool_registry, fallback=None, max_steps=6):
        history = []
        tools = tool_registry.schema_list() if tool_registry else []
        for step in range(max_steps):
            step_payload = {
                "original_payload": payload,
                "conversation_history": history,
                "available_tools": tools,
                "step": step,
            }
            response = self.complete_json(task, step_payload, fallback=None)
            if not isinstance(response, dict):
                break
            if "result" in response:
                return response["result"]
            if "tool_call" in response:
                call = response["tool_call"]
                obs = tool_registry.dispatch(call.get("name", ""), call.get("args", {})) if tool_registry else "No tools available"
                history.append({"step": step, "thought": response.get("thought", ""), "tool_call": call, "observation": obs})
                continue
            return response
        return fallback

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
