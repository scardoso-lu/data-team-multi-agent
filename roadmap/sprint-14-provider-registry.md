# Sprint 14 — Provider Registry & Model Swapping

## Gap

LangChain's harness anatomy emphasises provider agnosticity — the harness should
work with any LLM supporting tool calling, from frontier models to open-source,
and switching providers should require only configuration, not code changes.

`LocalLLMClient` in `shared_skills/llm_integration/` hard-codes a fixed try-list
of three CLIs (`codex`, `mistral`, `claude`) in source. Adding a new provider
(OpenAI API, Gemini, a locally-hosted model via Ollama) requires editing core
infrastructure code. There is no per-agent model configuration, no clean registry
interface, and no way to configure provider order without modifying `llm_integration`.

## Goal

Replace the hard-coded CLI list with a configuration-driven `ProviderRegistry`.
Define a `LLMProvider` protocol that any provider implements. Ship four built-in
providers: `ClaudeCLIProvider`, `CodexCLIProvider`, `MistralCLIProvider`, and
`OllamaProvider`. Allow per-agent model overrides via `config/default.json`.

---

## User Story 14.1 — `LLMProvider` protocol

**As a** platform engineer,
**I want** a typed interface that any LLM provider implements,
**so that** I can add new providers without touching `LocalLLMClient` or any
agent code.

### Implementation

**New file:** `shared_skills/llm_integration/providers.py`

```python
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        """Return True if the provider CLI or endpoint is reachable."""
        ...

    def complete(self, prompt: str, timeout: int = 30) -> Optional[str]:
        """
        Submit a prompt and return the raw text response, or None on failure.
        Must not raise; swallow provider-specific errors and return None.
        """
        ...
```

**Acceptance criteria:**
- Any class with `name`, `is_available()`, and `complete()` satisfies
  `isinstance(obj, LLMProvider)` at runtime.
- `complete` returns `None` (not raises) on any provider error.

**Tests:** `tests/test_provider_registry.py`
```python
def test_llm_provider_protocol_satisfied():
    class FakeProvider:
        name = "fake"
        def is_available(self): return True
        def complete(self, prompt, timeout=30): return '{"ok": true}'

    assert isinstance(FakeProvider(), LLMProvider)
```

---

## User Story 14.2 — `ProviderRegistry` with ordered provider list

**As a** `LocalLLMClient`,
**I want** a registry that holds an ordered list of providers and returns the
first available one,
**so that** provider selection is configuration-driven and can be changed without
editing `llm_integration`.

### Implementation

**New file:** `shared_skills/llm_integration/provider_registry.py`

```python
from typing import List, Optional
from shared_skills.llm_integration.providers import LLMProvider


class ProviderRegistry:
    def __init__(self, providers: List[LLMProvider] = None):
        self._providers = providers or []

    def register(self, provider: LLMProvider) -> None:
        self._providers.append(provider)

    def first_available(self) -> Optional[LLMProvider]:
        return next((p for p in self._providers if p.is_available()), None)

    def all_available(self) -> List[LLMProvider]:
        return [p for p in self._providers if p.is_available()]

    @classmethod
    def from_config(cls, provider_names: List[str]) -> "ProviderRegistry":
        """Build a registry from a list of provider name strings."""
        from shared_skills.llm_integration.builtin_providers import BUILTIN_PROVIDERS
        providers = [BUILTIN_PROVIDERS[name]() for name in provider_names
                     if name in BUILTIN_PROVIDERS]
        return cls(providers)
```

**Acceptance criteria:**
- `first_available()` returns the first provider whose `is_available()` is `True`.
- `first_available()` returns `None` when no providers are available.
- `from_config(["claude", "codex"])` builds a registry with those two providers in order.
- Unknown provider names in `from_config` are silently skipped.

**Tests:** `tests/test_provider_registry.py`
```python
def test_first_available_returns_first_ready_provider():
    p1 = _make_provider("p1", available=False)
    p2 = _make_provider("p2", available=True)
    p3 = _make_provider("p3", available=True)
    reg = ProviderRegistry([p1, p2, p3])
    assert reg.first_available().name == "p2"

def test_first_available_returns_none_when_all_unavailable():
    reg = ProviderRegistry([_make_provider("p1", available=False)])
    assert reg.first_available() is None
```

---

## User Story 14.3 — Four built-in providers

**As a** developer,
**I want** `ClaudeCLIProvider`, `CodexCLIProvider`, `MistralCLIProvider`, and
`OllamaProvider` shipped with the project,
**so that** the common cases work out of the box.

### Implementation

**New file:** `shared_skills/llm_integration/builtin_providers.py`

```python
import shutil
import subprocess
from shared_skills.llm_integration.providers import LLMProvider


class _CLIProvider:
    """Base for providers that shell out to a local CLI."""

    cli_name: str
    name: str

    def is_available(self) -> bool:
        return shutil.which(self.cli_name) is not None

    def complete(self, prompt: str, timeout: int = 30):
        try:
            result = subprocess.run(
                [self.cli_name, prompt],
                capture_output=True, text=True, timeout=timeout,
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None


class ClaudeCLIProvider(_CLIProvider):
    name = "claude"
    cli_name = "claude"


class CodexCLIProvider(_CLIProvider):
    name = "codex"
    cli_name = "codex"


class MistralCLIProvider(_CLIProvider):
    name = "mistral"
    cli_name = "mistral"


class OllamaProvider:
    """HTTP provider for locally-running Ollama server."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model

    def is_available(self) -> bool:
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2)
            return True
        except Exception:
            return False

    def complete(self, prompt: str, timeout: int = 30):
        import json
        import urllib.request
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False})
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read()).get("response")
        except Exception:
            return None


BUILTIN_PROVIDERS = {
    "claude": ClaudeCLIProvider,
    "codex": CodexCLIProvider,
    "mistral": MistralCLIProvider,
    "ollama": OllamaProvider,
}
```

**Acceptance criteria:**
- `ClaudeCLIProvider().is_available()` returns `True` iff `claude` is on `PATH`.
- `OllamaProvider().is_available()` returns `False` when no server is running (does
  not raise, returns within 3 seconds).
- `complete` always returns `None` (not raises) on any failure.

**Tests:** `tests/test_provider_registry.py`
```python
def test_cli_provider_unavailable_when_cli_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert ClaudeCLIProvider().is_available() is False

def test_ollama_provider_unavailable_when_server_down():
    provider = OllamaProvider(base_url="http://127.0.0.1:19999")
    assert provider.is_available() is False
```

---

## User Story 14.4 — Configuration-driven provider order and per-agent overrides

**As a** platform operator,
**I want** the provider order defined in `config/default.json` and overridable
per agent,
**so that** I can configure a fast local model for quick checks and a powerful
model for architecture design without code changes.

### Implementation

**File:** `config/default.json`

```json
"llm": {
  "providers": ["claude", "codex", "mistral"],
  "per_agent": {
    "data_architect": ["ollama", "claude"],
    "qa_engineer": ["codex", "mistral"]
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "llama3"
  }
}
```

**File:** `shared_skills/llm_integration/__init__.py`

Replace the hard-coded try-list in `LocalLLMClient` with `ProviderRegistry`:

```python
class LocalLLMClient:
    def __init__(self, config=None, agent_key=None):
        if config is not None:
            llm_config = config.require("llm", ...)
            per_agent = llm_config.get("per_agent", {})
            provider_names = per_agent.get(agent_key, llm_config.get("providers", []))
        else:
            provider_names = ["claude", "codex", "mistral"]
        self._registry = ProviderRegistry.from_config(provider_names)

    def complete_json(self, task, payload, fallback=None):
        provider = self._registry.first_available()
        if provider is None:
            return fallback
        prompt = self._build_prompt(task, payload)
        raw = provider.complete(prompt)
        return self._parse_json(raw) or fallback
```

**Acceptance criteria:**
- With `per_agent` override for `data_architect`, that agent uses the overridden
  provider list.
- Without per-agent override, the global `providers` list is used.
- With an empty `providers` list, `complete_json` returns `fallback`.
- Existing `HarnessLLMClient` (which bypasses `LocalLLMClient`) is unaffected.

**Tests:** `tests/test_llm_integration.py`
```python
def test_local_llm_client_uses_per_agent_override(monkeypatch):
    used = []
    monkeypatch.setattr(ProviderRegistry, "first_available",
                        lambda self: _make_recording_provider(used))
    config = _config_with_per_agent({"data_architect": ["ollama"]})
    client = LocalLLMClient(config=config, agent_key="data_architect")
    client.complete_json("task", {}, fallback={})
    # Assert "ollama" provider was selected, not default

def test_local_llm_client_returns_fallback_when_no_providers():
    client = LocalLLMClient(config=_config_with_providers([]))
    result = client.complete_json("task", {}, fallback={"default": True})
    assert result == {"default": True}
```
