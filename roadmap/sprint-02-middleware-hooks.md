# Sprint 2 — Middleware Hook System

## Gap
There are no composable `before_agent`, `before_model`, `after_model`, or `after_agent`
hooks. PII scrubbing exists only in debug log paths (`redact_debug_value`). Business
guardrails are embedded directly in `execute_stage`, not in a separable layer.
Teams owning security, compliance, and context management cannot plug in their logic
without editing core agent code.

## Goal
Introduce a `Middleware` protocol and a hook-dispatch mechanism in `BoardAgent`.
Ship three built-in middleware classes: PII scrubbing, context-size guard, and the
business-examples guardrail currently buried in `DataArchitectAgent`.

---

## User Story 2.1 — `Middleware` protocol and `BoardAgent` hook dispatch

**As a** platform engineer,
**I want** a standard middleware interface with ordered hook points,
**so that** any team can inject cross-cutting logic without touching core agent code.

### Implementation

**New file:** `shared_skills/middleware/__init__.py`

```python
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class Middleware(Protocol):
    def before_agent(self, context: Dict[str, Any]) -> Dict[str, Any]: ...
    def before_model(self, prompt: str, context: Dict[str, Any]) -> str: ...
    def after_model(self, response: Optional[str], context: Dict[str, Any]) -> Optional[str]: ...
    def after_agent(self, result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]: ...


class BaseMiddleware:
    """No-op base — override only the hooks you need."""
    def before_agent(self, context): return context
    def before_model(self, prompt, context): return prompt
    def after_model(self, response, context): return response
    def after_agent(self, result, context): return result
```

**File:** `shared_skills/agent_base/__init__.py`

Add to `BoardAgent.__init__`:
```python
self.middlewares: list = list(middlewares or [])
```

Add to `BoardAgent.__init__` signature:
```python
def __init__(self, *, middlewares=None, ...):
```

Add dispatch helpers:
```python
def _run_before_agent(self, context):
    for mw in self.middlewares:
        context = mw.before_agent(context)
    return context

def _run_before_model(self, prompt, context):
    for mw in self.middlewares:
        prompt = mw.before_model(prompt, context)
    return prompt

def _run_after_model(self, response, context):
    for mw in self.middlewares:
        response = mw.after_model(response, context)
    return response

def _run_after_agent(self, result, context):
    for mw in reversed(self.middlewares):
        result = mw.after_agent(result, context)
    return result
```

Call `_run_before_agent` at the top of `process_next_item` and `_run_after_agent`
before returning the result dict.

**Acceptance criteria:**
- A list of middlewares can be passed to any agent constructor.
- Hooks execute in registration order (`before_*`) and reverse order (`after_*`).
- An agent with no middlewares behaves identically to today.

**Tests:** `tests/test_middleware.py` (new file)
- Instantiate `DataArchitectAgent(middlewares=[stub_mw])`.
- Assert `stub_mw.before_agent` was called with a context dict.
- Assert `stub_mw.after_agent` was called with the result dict.

---

## User Story 2.2 — `PIIScrubbingMiddleware` (`before_model` hook)

**As a** security engineer,
**I want** PII patterns stripped from every LLM prompt before it is sent,
**so that** customer data, tokens, and credentials never reach an external CLI.

### Implementation

**New file:** `shared_skills/middleware/pii.py`

```python
import re
from shared_skills.middleware import BaseMiddleware

_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<ssn>"),
    (re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\b"), "<cc>"),
    (re.compile(r"(?i)(secret|token|password|pat|key)\s*[:=]\s*\S+"), r"\1=<redacted>"),
]

class PIIScrubbingMiddleware(BaseMiddleware):
    def before_model(self, prompt, context):
        for pattern, replacement in _PATTERNS:
            prompt = pattern.sub(replacement, prompt)
        return prompt
```

Wire it as the first entry in `middlewares` list for all agents (or via config).

**Acceptance criteria:**
- Email addresses in the prompt are replaced with `<email>`.
- `secret=abc123` patterns are replaced with `secret=<redacted>`.
- Non-PII prompt text is unchanged.

**Tests:** `tests/test_middleware.py`
- Pass a prompt containing an email, an SSN, and a token pattern.
- Assert all three are scrubbed.
- Assert the rest of the prompt is unchanged.

---

## User Story 2.3 — `ContextSizeMiddleware` (`before_model` hook)

**As a** platform engineer,
**I want** prompts truncated when they exceed a configured character budget,
**so that** the LLM CLI never receives a payload that would overflow its context window.

### Implementation

**New file:** `shared_skills/middleware/context_size.py`

```python
from shared_skills.middleware import BaseMiddleware

DEFAULT_MAX_CHARS = 120_000   # ~30K tokens at 4 chars/token

class ContextSizeMiddleware(BaseMiddleware):
    def __init__(self, max_chars=None, config=None):
        configured = config.get("llm", "max_prompt_chars") if config else None
        self.max_chars = max_chars or configured or DEFAULT_MAX_CHARS

    def before_model(self, prompt, context):
        if len(prompt) <= self.max_chars:
            return prompt
        truncated = prompt[: self.max_chars]
        return truncated + "\n\n[PROMPT TRUNCATED — payload exceeded context budget]"
```

**Config addition** (`config/default.json`, under `llm`):
```json
"max_prompt_chars": 120000
```

**Acceptance criteria:**
- Prompts under the limit pass through unchanged.
- Prompts over the limit are truncated and a `[PROMPT TRUNCATED]` marker is appended.
- The `max_chars` value is read from config when not passed directly.

**Tests:** `tests/test_middleware.py`
- Assert a short prompt is returned unchanged.
- Assert a prompt of `max_chars + 1` is truncated to exactly `max_chars` chars plus the marker.

---

## User Story 2.4 — `BusinessExamplesGuardrailMiddleware` (`before_agent` hook)

**As a** data architect agent,
**I want** the business I/O examples check extracted into a middleware,
**so that** the guardrail is testable in isolation and reusable by other agents.

### Implementation

**New file:** `shared_skills/middleware/guardrails.py`

```python
from agent_runtime import WorkItemBlocked
from artifacts import extract_business_io_examples, is_human_confirmed_exploration
from shared_skills.middleware import BaseMiddleware

class BusinessExamplesGuardrailMiddleware(BaseMiddleware):
    def before_agent(self, context):
        requirements = context.get("stage_input", {})
        try:
            extract_business_io_examples(requirements)
        except ValueError as exc:
            if is_human_confirmed_exploration(requirements):
                return context   # exploration path — let agent handle it
            raise WorkItemBlocked("missing_business_io_examples", str(exc)) from exc
        return context
```

Remove the equivalent block from `DataArchitectAgent.design_architecture` and add this
middleware to the architect's `middlewares` list.

**Acceptance criteria:**
- A work item without examples raises `WorkItemBlocked` via the middleware, not inside `execute_stage`.
- A human-confirmed exploration topic passes through without error.
- `design_architecture` no longer contains the example-check logic.

**Tests:** `tests/test_middleware.py`
- Assert `WorkItemBlocked` is raised for a context with no examples.
- Assert no exception for an exploration-confirmed context.
`tests/test_data_architect.py`
- Existing `test_data_architect_blocks_when_business_io_examples_are_missing` still passes.
