# Sprint 6 — Context Management & Summarisation

## Gap
Artifact payloads are passed verbatim to the LLM CLI. As work items accumulate more
business examples, user stories, and multi-stage upstream artifacts the prompt will
silently exceed the CLI context window. There is no summarisation, no field-level
truncation strategy, and no token-budget awareness. Sprint 2 added a hard character
truncation guard; this sprint introduces intelligent summarisation so that semantically
important content is preserved rather than cut off arbitrarily.

## Goal
Before each model call, estimate the prompt size. If it exceeds the budget, summarise
or compress the heaviest fields while keeping contracts, examples, and acceptance
criteria intact. Provide both an LLM-based summariser (when a CLI is available) and a
deterministic fallback (when offline).

---

## User Story 6.1 — Payload size estimator utility

**As a** middleware component,
**I want** a utility that estimates the token count of a JSON payload,
**so that** downstream logic can decide whether summarisation is needed without making
an LLM call just to measure size.

### Implementation

**New file:** `shared_skills/context/__init__.py`

```python
import json

# Rough approximation: 1 token ≈ 4 characters for English text.
CHARS_PER_TOKEN = 4


def estimate_tokens(payload) -> int:
    """Return an estimated token count for a dict or string."""
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False)
    return len(text) // CHARS_PER_TOKEN


def payload_exceeds_budget(payload, max_tokens: int) -> bool:
    return estimate_tokens(payload) > max_tokens
```

**Config addition** (`config/default.json`, under `llm`):
```json
"max_payload_tokens": 30000
```

**Acceptance criteria:**
- `estimate_tokens("hello world")` returns `2` (11 chars / 4 ≈ 2).
- `payload_exceeds_budget(large_dict, 100)` returns `True` when estimated tokens > 100.

**Tests:** `tests/test_context.py` (new file)
- Assert `estimate_tokens` returns a positive int for a non-empty dict.
- Assert `payload_exceeds_budget` returns `False` for a tiny payload.

---

## User Story 6.2 — Deterministic payload compressor

**As a** middleware component,
**I want** a deterministic compressor that shortens heavy free-text fields without
removing structured contract data (examples, acceptance criteria, pipelines),
**so that** the system stays offline-safe even without a live LLM summariser.

### Implementation

**File:** `shared_skills/context/__init__.py`

```python
# Fields considered structural — never truncate.
PROTECTED_KEYS = {
    "business_io_examples",
    "acceptance_criteria",
    "user_stories",
    "tables",
    "relationships",
    "pipelines",
    "execution_mode",
}

MAX_FREE_TEXT_CHARS = 2000   # per field


def compress_payload(payload: dict) -> dict:
    """Truncate long string values in non-protected keys."""
    if not isinstance(payload, dict):
        return payload
    result = {}
    for key, value in payload.items():
        if key in PROTECTED_KEYS:
            result[key] = value
        elif isinstance(value, str) and len(value) > MAX_FREE_TEXT_CHARS:
            result[key] = value[:MAX_FREE_TEXT_CHARS] + " [truncated]"
        elif isinstance(value, dict):
            result[key] = compress_payload(value)
        else:
            result[key] = value
    return result
```

**Acceptance criteria:**
- A field in `PROTECTED_KEYS` is never truncated regardless of length.
- A long free-text field is truncated to `MAX_FREE_TEXT_CHARS` with `[truncated]` suffix.
- Nested dicts are recursively compressed.

**Tests:** `tests/test_context.py`
- Assert a 5000-char description field is truncated.
- Assert `business_io_examples` with 5000-char values is returned unchanged.
- Assert nested dict keys are recursively processed.

---

## User Story 6.3 — `SummarisationMiddleware` with LLM-based and fallback paths

**As a** platform engineer,
**I want** a middleware that summarises oversized payloads before the model call,
**so that** the LLM always receives a prompt within its context budget.

### Implementation

**New file:** `shared_skills/middleware/summarisation.py`

```python
import json
from context import compress_payload, estimate_tokens, payload_exceeds_budget
from shared_skills.middleware import BaseMiddleware


class SummarisationMiddleware(BaseMiddleware):
    """Compress or summarise the payload section of the prompt when over budget."""

    def __init__(self, max_tokens=None, config=None, llm=None):
        configured = config.get("llm", "max_payload_tokens") if config else None
        self.max_tokens = max_tokens or configured or 30_000
        self.llm = llm   # optional — used for LLM-based summarisation

    def before_model(self, prompt, context):
        payload = context.get("payload")
        if payload is None or not payload_exceeds_budget(payload, self.max_tokens):
            return prompt

        if self.llm is not None:
            compressed = self._llm_summarise(payload)
        else:
            compressed = compress_payload(payload)

        context["payload"] = compressed
        # Rebuild the prompt section that contains the payload.
        # The prompt structure is: "Task:\n...\nInput JSON:\n{payload}\n..."
        # Replace only the Input JSON block.
        try:
            before, after = prompt.split("Input JSON:\n", 1)
            original_json_end = after.index("\n\nConstraints:")
            new_payload_text = json.dumps(compressed, indent=2, sort_keys=True)
            return (
                before
                + "Input JSON:\n"
                + new_payload_text
                + after[original_json_end:]
            )
        except (ValueError, KeyError):
            return prompt   # cannot parse structure — return unchanged

    def _llm_summarise(self, payload):
        summary = self.llm.complete_json(
            task=(
                "Summarise the following payload to reduce its size while preserving "
                "all structured fields (business_io_examples, acceptance_criteria, "
                "user_stories, tables, relationships, pipelines). "
                "Shorten only free-text description fields."
            ),
            payload={"payload": payload},
            fallback=compress_payload(payload),   # offline fallback
        )
        return summary if isinstance(summary, dict) else compress_payload(payload)
```

**Acceptance criteria:**
- When the payload fits within the budget, the prompt is unchanged.
- When the payload exceeds the budget and `llm=None`, `compress_payload` is applied.
- When the payload exceeds the budget and an LLM is provided, the LLM summarises.
- `business_io_examples` is never removed regardless of payload size.

**Tests:** `tests/test_middleware.py`
- Build a payload with a 10 000-char description and protected `business_io_examples`.
- Assert `before_model` returns a shorter prompt.
- Assert `business_io_examples` is present in the modified prompt text.

---

## User Story 6.4 — Wire `SummarisationMiddleware` into agent construction

**As a** board agent,
**I want** summarisation active by default when the payload budget is exceeded,
**so that** I do not need to manually opt in for each new agent or work item.

### Implementation

**File:** Each agent's `app.py`

Add `SummarisationMiddleware` to the agent's middleware list after `ContextSizeMiddleware`:

```python
from middleware.summarisation import SummarisationMiddleware

# In __init__, after self.llm is set:
summarisation_mw = SummarisationMiddleware(config=self.config, llm=self.llm)
self.middlewares.append(summarisation_mw)
```

The order should be:
1. `MemoryMiddleware` — inject memory first
2. `PIIScrubbingMiddleware` — scrub after memory injection
3. `SummarisationMiddleware` — compress after scrubbing
4. `ContextSizeMiddleware` — hard cap as final guard

**Acceptance criteria:**
- All five agents have `SummarisationMiddleware` in their middleware chain.
- Running the test suite (`uv run pytest tests/ -v`) passes with no regressions.

**Tests:** `tests/test_harness_workflow.py`
- Add a work item whose description exceeds `max_payload_tokens`.
- Assert the harness completes successfully (falls back to deterministic compress).


## Implementation Status

- [x] Sprint implementation completed in codebase
