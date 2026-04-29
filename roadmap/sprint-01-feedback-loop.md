# Sprint 1 — Self-Correcting Feedback Loop

## Gap
When `validate_artifact()` raises after `execute_stage()`, `retry_operation` blindly
re-runs `execute_stage` with the identical prompt and payload. The validation error
is never shown to the LLM. The model has no opportunity to self-correct.

## Goal
After each failed validation the LLM receives the error message as an observation and
produces a revised artifact. Hard-failure retries (network errors, etc.) remain separate
from correction retries so the two budgets do not interfere.

---

## User Story 1.1 — Correction prompt builder in `LocalLLMClient`

**As a** board agent,
**I want** to re-prompt the LLM with the previous response and the validation error,
**so that** the model can produce a corrected artifact without losing prior context.

### Implementation

**File:** `shared_skills/llm_integration/__init__.py`

Add a `complete_json_with_correction` method:

```python
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
```

**Acceptance criteria:**
- When called with `previous_response` and `error`, the prompt sent to the LLM contains both.
- When called without them, behaviour is identical to the existing `complete_json`.
- The fallback fires if the LLM still returns non-JSON after correction.

**Tests:** `tests/test_llm_integration.py`
- Assert that the correction prompt contains `"validation_error"` key.
- Assert that a corrected JSON response is returned and parsed.
- Assert that the fallback is returned when correction also fails.

---

## User Story 1.2 — Correction loop in `BoardAgent.process_next_item`

**As a** board agent,
**I want** up to `N` correction attempts after a validation failure before giving up,
**so that** transient LLM formatting errors are recovered automatically.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

Replace the current single `validate_artifact` call with a correction loop:

```python
MAX_CORRECTION_ATTEMPTS = 2   # read from config: runtime.max_correction_attempts

artifact = retry_operation(
    lambda: self.execute_stage(stage_input),
    max_retries,
    retry_delay,
)

last_error = None
for attempt in range(MAX_CORRECTION_ATTEMPTS + 1):
    try:
        self.validate_artifact(artifact)
        break                          # valid — continue normally
    except (ValueError, KeyError) as exc:
        if attempt == MAX_CORRECTION_ATTEMPTS:
            raise                      # exhausted — propagate to failure_result
        last_error = exc
        artifact = self.correct_artifact(artifact, last_error)

# continue to save_artifact / request_approval ...
```

Add `correct_artifact` template method to `BoardAgent`:

```python
def correct_artifact(self, artifact, error):
    """Override in concrete agents to re-prompt the LLM with the error."""
    return artifact    # default: return unchanged (no LLM available)
```

**Config addition** (`config/default.json`, under `runtime`):
```json
"max_correction_attempts": 2
```

**Acceptance criteria:**
- A first validation failure triggers `correct_artifact`, not an immediate exception.
- After `max_correction_attempts` the item is routed to the error column as before.
- A successful correction on attempt 2 produces a `"processed"` result.

**Tests:** `tests/test_process_next_item.py`
- Inject a `FakeBoardClient` whose `get_work_item_details` returns a payload that makes
  the first LLM call produce an invalid artifact and the second produce a valid one.
- Assert the final result status is `"processed"`.
- Assert the error column is used only after all correction attempts are exhausted.

---

## User Story 1.3 — Concrete `correct_artifact` in each agent

**As a** data architect agent,
**I want** to send my previous artifact draft and the validation error back to the LLM,
**so that** the corrected architecture artifact satisfies the contract.

### Implementation

Override `correct_artifact` in every concrete agent. Example for `DataArchitectAgent`:

**File:** `agents/data_architect/app.py`

```python
def correct_artifact(self, artifact, error):
    logger.warning(
        "Artifact validation failed for work item %s: %s. Attempting correction.",
        self.work_item_id, error,
    )
    fallback = self.config.copy_value("architecture", default={})
    return self.llm.complete_json_with_correction(
        task=load_task("data_architect"),
        payload={"requirements": artifact},
        fallback=fallback,
        previous_response=artifact,
        error=error,
    )
```

Apply the same pattern to `DataEngineerAgent`, `QAEngineerAgent`, `DataAnalystAgent`,
and `DataStewardAgent` using their respective tasks and fallbacks.

**Acceptance criteria:**
- Each agent's `correct_artifact` passes the failed artifact and error to `complete_json_with_correction`.
- Agents without an `llm` attribute (future agents) fall back to the base no-op.

**Tests:** One test per agent in the existing `tests/test_<role>.py` files:
- Inject an `llm` stub whose first call returns an invalid artifact and second returns a valid one.
- Assert that `process_next_item` returns `"processed"` status.

---

## User Story 1.4 — Emit a correction event

**As a** platform operator,
**I want** a structured event every time a correction attempt fires,
**so that** I can track how often agents need self-correction in production.

### Implementation

**File:** `shared_skills/events/__init__.py`

Add constant:
```python
ARTIFACT_CORRECTION_ATTEMPTED = "artifact_correction_attempted"
```

**File:** `shared_skills/agent_base/__init__.py`

In the correction loop, emit before calling `correct_artifact`:
```python
self.events.emit(
    ARTIFACT_CORRECTION_ATTEMPTED,
    self.agent_key,
    work_item_id,
    attempt=attempt,
    error=str(last_error),
)
```

**Acceptance criteria:**
- `EventRecorder.events` contains an `artifact_correction_attempted` entry when a correction fires.
- The event payload includes `attempt` (int) and `error` (str).

**Tests:** `tests/test_events.py`
- Assert the new constant exists.
- Assert the event is recorded during a process_next_item correction cycle.
