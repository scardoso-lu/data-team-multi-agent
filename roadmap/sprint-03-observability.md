# Sprint 3 — LLM Observability

## Gap
`EventRecorder` captures seven board-lifecycle events but records nothing about LLM
interactions. After a run it is impossible to tell which CLI provider fired, how long
the call took, whether the deterministic fallback was used, or what error the CLI
returned. In production you cannot distinguish "LLM produced a great answer" from
"LLM was unavailable and the fallback silently fired for every agent."

## Goal
Emit structured events for every `complete_json` / `complete_text` call. Record
provider, latency, fallback flag, and raw CLI error when present. Surface a summary
in the harness output.

---

## User Story 3.1 — Add LLM event constants

**As a** platform operator,
**I want** named constants for LLM call lifecycle events,
**so that** event consumers can pattern-match without using raw strings.

### Implementation

**File:** `shared_skills/events/__init__.py`

Add:
```python
LLM_CALL_STARTED   = "llm_call_started"
LLM_CALL_COMPLETED = "llm_call_completed"
LLM_CALL_FAILED    = "llm_call_failed"
```

**Acceptance criteria:**
- The three constants are importable from `events`.

**Tests:** `tests/test_events.py`
- Assert each constant equals its string value.

---

## User Story 3.2 — Instrument `LocalLLMClient` with an event sink

**As a** platform operator,
**I want** `LocalLLMClient` to emit `llm_call_started` and `llm_call_completed` events,
**so that** I can observe provider selection, latency, and fallback usage per agent call.

### Implementation

**File:** `shared_skills/llm_integration/__init__.py`

Add optional `events` and `agent` parameters to `LocalLLMClient.__init__`:
```python
def __init__(self, config=None, commands=None, timeout_seconds=None, events=None, agent=None):
    ...
    self.events = events        # any object with .emit(type, agent, **payload)
    self.agent = agent or "unknown"
```

Wrap `complete_json` to time the call and emit events:
```python
def complete_json(self, task, payload, fallback=None):
    import time
    start = time.monotonic()
    if self.events:
        self.events.emit(LLM_CALL_STARTED, self.agent, task=task[:120])

    prompt = self._build_prompt(task, payload, response_format="json")
    raw = self._run_first_available(prompt)

    latency_ms = int((time.monotonic() - start) * 1000)
    used_fallback = raw is None

    parsed = None
    if raw:
        parsed = extract_json(raw)
        if parsed is None:
            used_fallback = True

    if self.events:
        self.events.emit(
            LLM_CALL_COMPLETED,
            self.agent,
            task=task[:120],
            latency_ms=latency_ms,
            fallback_used=used_fallback,
            provider=self._last_provider,    # see US 3.3
        )

    return parsed if not used_fallback else fallback
```

**Acceptance criteria:**
- Every `complete_json` call emits `llm_call_started` then `llm_call_completed`.
- `fallback_used=True` when no CLI is available or response is non-JSON.
- `fallback_used=False` when the LLM produces valid JSON.
- `latency_ms` is a positive integer.

**Tests:** `tests/test_llm_integration.py`
- Inject an `EventRecorder` as `events=`.
- Assert two events are emitted per `complete_json` call.
- Assert `fallback_used=True` when all CLIs are missing.

---

## User Story 3.3 — Track which provider responded

**As a** platform operator,
**I want** the event payload to include the name of the CLI that responded,
**so that** I can identify which provider is being used and compare reliability.

### Implementation

**File:** `shared_skills/llm_integration/__init__.py`

Add `self._last_provider = None` to `__init__`.

In `_run_first_available`, record the provider when a CLI succeeds:
```python
if completed.returncode == 0 and completed.stdout.strip():
    self._last_provider = command.provider
    return completed.stdout.strip()
```

When fallback fires, `_last_provider` remains `None`.

Include in `llm_call_completed` event payload:
```python
provider=self._last_provider,   # None means fallback
```

**Acceptance criteria:**
- `provider` is `"codex"`, `"claude"`, or `"mistral"` when a CLI responds.
- `provider` is `None` when the fallback fires.

**Tests:** `tests/test_llm_integration.py`
- Stub `shutil.which` and `subprocess.run` to simulate a successful codex call.
- Assert `provider="codex"` in the `llm_call_completed` event.

---

## User Story 3.4 — Pass the event sink from agents to `LocalLLMClient`

**As a** board agent,
**I want** `LocalLLMClient` to share my event sink,
**so that** LLM events are recorded alongside board lifecycle events in the same stream.

### Implementation

**File:** `agents/data_architect/app.py` (and all other agent `app.py` files)

Pass `events` and `agent` when constructing the LLM client:
```python
self.llm = llm or LocalLLMClient(
    config=self.config,
    events=self.events,
    agent=self.agent_key,
)
```

Apply the same change to `DataEngineerAgent`, `QAEngineerAgent`, `DataAnalystAgent`,
and `DataStewardAgent`.

**Acceptance criteria:**
- Running the harness (`uv run python -m harness.run`) with `events.sink=memory` in config
  produces `llm_call_started` and `llm_call_completed` events in `EventRecorder.events`.
- Events include the correct `agent` value for each pipeline stage.

**Tests:** `tests/test_harness_workflow.py`
- After `run_once()`, assert `events.events` contains at least one `llm_call_completed` event.
- Assert that event's `fallback_used=True` (harness LLM always uses fallback).

---

## User Story 3.5 — Print observability summary from the harness

**As a** developer running the local harness,
**I want** a summary of LLM calls printed at the end,
**so that** I can quickly confirm the pipeline ran with real LLM output or fallbacks.

### Implementation

**File:** `harness/run.py`

After `run_once()` completes, add:
```python
def _print_llm_summary(events):
    llm_events = [e for e in events.events if e["type"] == "llm_call_completed"]
    print("\n=== LLM Call Summary ===")
    for evt in llm_events:
        p = evt["payload"]
        status = "FALLBACK" if p.get("fallback_used") else f"OK ({p.get('provider')})"
        print(f"  [{evt['agent']}] {status}  {p.get('latency_ms', '?')}ms")
    if not llm_events:
        print("  No LLM calls recorded.")
```

Call `_print_llm_summary(harness["events"])` in `main()`.

**Acceptance criteria:**
- Running `make harness` prints a `=== LLM Call Summary ===` block.
- Each row shows agent name, provider or FALLBACK, and latency.

**Tests:** No automated test required for console output; covered by manual harness run.


## Implementation Status

- [x] Sprint implementation completed in codebase
