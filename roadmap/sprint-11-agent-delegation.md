# Sprint 11 — Agent Delegation & Subagents

## Gap

LangChain's harness anatomy includes a `task` tool for spawning subagents with
isolated context windows. This allows complex work to be offloaded to a
specialised agent — for example, a data architect spawning a "table schema
designer" subagent for each table independently, then merging results — without
the full upstream context polluting the subagent's context window.

The current pipeline is strictly linear and synchronous. Every agent receives
the complete upstream artifact verbatim. There is no mechanism for an agent to
delegate a subset of its work to another agent instance, and no way to run
multiple subagents in parallel over disjoint slices of a work item.

## Goal

Introduce an `AgentTaskDispatcher` that lets any `BoardAgent` spawn a child agent
by name, pass it a scoped payload, and receive a typed result back. Add a
`delegate_task` tool to the `ToolRegistry` (Sprint 7) so the LLM can request
delegation as a TAO action. Keep dispatch synchronous in this sprint; parallelism
is an extension.

---

## User Story 11.1 — `AgentTaskDispatcher` for in-process subagent invocation

**As a** board agent,
**I want** to spawn a named child agent with a scoped payload and collect its result,
**so that** I can break large tasks into independently-scoped subtasks without
forwarding my entire context to the child.

### Implementation

**New file:** `shared_skills/delegation/__init__.py`

```python
from typing import Any, Dict


class AgentTaskDispatcher:
    """Synchronous in-process subagent dispatcher."""

    def __init__(self, agent_factory, llm, config, events=None):
        """
        agent_factory: callable(agent_key) -> BoardAgent instance
        llm: shared LLM client forwarded to child agents
        config: AppConfig
        events: optional EventRecorder (child events flow into the same recorder)
        """
        self._factory = agent_factory
        self._llm = llm
        self._config = config
        self._events = events

    def dispatch(self, agent_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instantiate `agent_key`, call execute_stage(payload), validate the
        result, and return the artifact dict.

        Raises ValueError if agent_key is unknown.
        Raises the agent's own exceptions on validation failure.
        """
        agent = self._factory(agent_key)
        artifact = agent.execute_stage(payload)
        artifact = agent.validate_artifact(artifact)
        return artifact
```

**Acceptance criteria:**
- `dispatch("data_architect", {...})` returns a valid architecture artifact.
- Unknown `agent_key` raises `ValueError`.
- Child agent events flow into the parent's `EventRecorder`.
- No ADO board operations occur during dispatch (child does not call
  `claim_work_item`, `move_work_item`, or `request_approval`).

**Tests:** `tests/test_delegation.py`
```python
def test_dispatcher_calls_child_execute_stage(monkeypatch):
    called_with = []

    class FakeAgent:
        def execute_stage(self, payload):
            called_with.append(payload)
            return {"tables": [], "relationships": [], "business_io_examples": [],
                    "user_stories": []}
        def validate_artifact(self, artifact):
            return artifact

    dispatcher = AgentTaskDispatcher(
        agent_factory=lambda key: FakeAgent(),
        llm=None, config=AppConfig(),
    )
    result = dispatcher.dispatch("data_architect", {"requirements_summary": "x"})
    assert called_with[0]["requirements_summary"] == "x"
```

---

## User Story 11.2 — `delegate_task` tool for LLM-triggered delegation

**As an** LLM running inside a TAO loop,
**I want** a `delegate_task` tool that I can call with `agent_key` and `payload`,
**so that** I can assign a specialist subagent to handle a scoped portion of my work
and receive its structured result as a TAO observation.

### Implementation

**New file:** `shared_skills/delegation/tools.py`

```python
import json
from shared_skills.delegation import AgentTaskDispatcher
from shared_skills.tools import Tool


def make_delegation_tool(dispatcher: AgentTaskDispatcher) -> Tool:
    def delegate_task(agent_key: str, payload: str) -> str:
        """
        payload must be a JSON string.
        Returns the child artifact serialised as JSON, or an error string.
        """
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            return f"ERROR: payload must be valid JSON — {exc}"
        try:
            result = dispatcher.dispatch(agent_key, parsed)
            return json.dumps(result)
        except ValueError as exc:
            return f"ERROR: {exc}"

    return Tool(
        name="delegate_task",
        description=(
            "Delegate a subtask to a specialist agent. "
            "agent_key: one of requirements_analyst, data_architect, data_engineer, "
            "qa_engineer, data_analyst, data_steward. "
            "payload: JSON string of the input for that agent's execute_stage. "
            "Returns the child artifact as a JSON string."
        ),
        parameters={
            "agent_key": "str — the agent to delegate to",
            "payload": "str — JSON-encoded input payload",
        },
        fn=delegate_task,
    )
```

**Acceptance criteria:**
- `delegate_task` with a valid `agent_key` and JSON `payload` returns a JSON string.
- Invalid JSON in `payload` returns an `"ERROR: payload must be valid JSON"` string
  (does not raise).
- Unknown `agent_key` returns an `"ERROR: ..."` string (does not raise).

**Tests:** `tests/test_delegation.py`
```python
def test_delegate_tool_returns_json_on_success():
    ...

def test_delegate_tool_returns_error_on_bad_json():
    ...

def test_delegate_tool_returns_error_on_unknown_key():
    ...
```

---

## User Story 11.3 — `DataArchitectAgent` uses delegation for per-table design

**As a** data architect,
**I want** to spawn a "table schema designer" subtask for each table independently,
**so that** the LLM focuses on one table at a time, reducing hallucination from
trying to hold the full multi-table schema in a single prompt.

### Implementation

**File:** `agents/data_architect/app.py`

Add a `_design_table(table_name, business_context)` helper that dispatches
to a lightweight internal function (not a full board agent) via
`AgentTaskDispatcher` or a direct `complete_json` call with a narrow prompt:

```python
def _design_table(self, table_name: str, context: dict) -> dict:
    """Design a single table schema using a focused LLM call."""
    payload = {
        "table_name": table_name,
        "business_context": context,
        "instruction": "Design the columns, types, and primary key for this table only.",
    }
    fallback = {"name": table_name, "columns": [], "primary_key": "id"}
    return self.llm.complete_json(
        task=f"Design table schema for {table_name}",
        payload=payload,
        fallback=fallback,
    )
```

Aggregate the per-table results in `design_architecture` and merge into the
final artifact.

**Acceptance criteria:**
- `design_architecture` produces one LLM call per table name extracted from the
  work item.
- Each table dict in the returned artifact has `name`, `columns`, `primary_key`.
- The harness test suite continues to pass (fallback path per-table is empty columns).

---

## User Story 11.4 — Child agent event isolation

**As a** platform operator,
**I want** child agent events tagged with `parent_agent` and `depth` fields,
**so that** I can distinguish root pipeline events from delegation events in the
`EventRecorder` without ambiguity.

### Implementation

**File:** `shared_skills/delegation/__init__.py`

Wrap each dispatched event with extra payload fields before passing to the
shared recorder:

```python
# In dispatch(), after creating the child agent, inject context into its events:
child_events_context = {
    "parent_agent": self._parent_agent_key,
    "depth": self._depth + 1,
}
```

**File:** `shared_skills/events/__init__.py`

Add constants:
```python
AGENT_DELEGATION_STARTED   = "agent_delegation_started"
AGENT_DELEGATION_COMPLETED = "agent_delegation_completed"
AGENT_DELEGATION_FAILED    = "agent_delegation_failed"
```

**Acceptance criteria:**
- `EventRecorder.events` contains `agent_delegation_started` before the child
  runs and `agent_delegation_completed` after.
- Each event has `parent_agent` and `depth` in its payload.
- `depth=0` for root pipeline agents, `depth=1` for directly-dispatched children.

**Tests:** `tests/test_delegation.py`
```python
def test_delegation_events_tagged_with_depth(monkeypatch):
    events = EventRecorder()
    dispatcher = AgentTaskDispatcher(..., events=events)
    dispatcher.dispatch("data_architect", {...})
    delegation_events = [e for e in events.events
                         if e["type"] == AGENT_DELEGATION_STARTED]
    assert delegation_events[0]["payload"]["depth"] == 1
```
