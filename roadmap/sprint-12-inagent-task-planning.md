# Sprint 12 — In-Agent Task Planning

## Gap

LangChain's harness anatomy highlights `write_todos` as a core planning primitive:
the model breaks its work into a structured task list, marks steps complete as it
proceeds, and can revisit unfinished steps in subsequent TAO iterations. This drives
reliable multi-step execution because the model does not have to hold an informal
plan in its prose reasoning.

Currently agents produce a single artifact in one (or a few) LLM calls. There is no
structured task list that the agent maintains during execution, no way to mark a step
complete and move to the next, and no mechanism for the TAO loop (Sprint 7) to surface
"what step am I on?" in the observation.

## Goal

Introduce an `AgentTodoTracker` that agents can use to write a plan, mark steps
complete, and query remaining work. Expose `write_todos`, `complete_todo`, and
`list_todos` as named tools in the `ToolRegistry`. Emit structured events so the
`EventRecorder` captures plan state at each TAO iteration.

---

## User Story 12.1 — `AgentTodoTracker` data model

**As a** board agent running a TAO loop,
**I want** a structured todo list I can write and update during execution,
**so that** the model's planning state is explicit and inspectable, not buried in
prose reasoning.

### Implementation

**New file:** `shared_skills/planning/__init__.py`

```python
from dataclasses import dataclass, field
from typing import List, Optional
from time import time
import uuid


@dataclass
class TodoItem:
    id: str
    description: str
    status: str = "pending"       # pending | in_progress | done | skipped
    created_at: float = field(default_factory=time)
    completed_at: Optional[float] = None
    notes: str = ""

    def complete(self, notes: str = ""):
        self.status = "done"
        self.completed_at = time()
        self.notes = notes

    def skip(self, reason: str = ""):
        self.status = "skipped"
        self.notes = reason

    def start(self):
        self.status = "in_progress"


class AgentTodoTracker:
    """Lightweight in-memory task tracker for a single agent execution."""

    def __init__(self):
        self._items: List[TodoItem] = []

    def write_todos(self, descriptions: List[str]) -> None:
        """Replace the current todo list with a new set of items."""
        self._items = [
            TodoItem(id=str(uuid.uuid4())[:8], description=d)
            for d in descriptions
        ]

    def start_todo(self, item_id: str) -> None:
        self._get(item_id).start()

    def complete_todo(self, item_id: str, notes: str = "") -> None:
        self._get(item_id).complete(notes)

    def skip_todo(self, item_id: str, reason: str = "") -> None:
        self._get(item_id).skip(reason)

    def pending(self) -> List[TodoItem]:
        return [i for i in self._items if i.status == "pending"]

    def in_progress(self) -> List[TodoItem]:
        return [i for i in self._items if i.status == "in_progress"]

    def all_done(self) -> bool:
        return all(i.status in ("done", "skipped") for i in self._items)

    def summary(self) -> str:
        lines = []
        for item in self._items:
            mark = {"pending": "[ ]", "in_progress": "[~]",
                    "done": "[x]", "skipped": "[-]"}.get(item.status, "[ ]")
            lines.append(f"{mark} [{item.id}] {item.description}")
            if item.notes:
                lines.append(f"       {item.notes}")
        return "\n".join(lines) if lines else "(no todos)"

    def to_dict(self) -> list:
        return [vars(i) for i in self._items]

    def _get(self, item_id: str) -> TodoItem:
        for item in self._items:
            if item.id == item_id:
                return item
        raise KeyError(f"No todo with id {item_id!r}")
```

**Acceptance criteria:**
- `write_todos(["a", "b"])` creates two `TodoItem`s with status `pending`.
- `complete_todo` sets `status="done"` and records `completed_at`.
- `all_done()` returns `True` only when every item is `done` or `skipped`.
- `summary()` renders a readable checklist with status marks.

**Tests:** `tests/test_planning.py`
```python
def test_write_and_complete_todos():
    tracker = AgentTodoTracker()
    tracker.write_todos(["design schema", "validate examples"])
    tracker.start_todo(tracker.pending()[0].id)
    tracker.complete_todo(tracker.in_progress()[0].id, notes="3 tables")
    assert tracker.pending()[0].description == "validate examples"
    assert not tracker.all_done()

def test_all_done_when_all_items_resolved():
    tracker = AgentTodoTracker()
    tracker.write_todos(["step 1", "step 2"])
    for item in tracker.pending():
        tracker.complete_todo(item.id)
    assert tracker.all_done()
```

---

## User Story 12.2 — `write_todos`, `complete_todo`, `list_todos` tools for `ToolRegistry`

**As an** LLM running inside a TAO loop,
**I want** `write_todos`, `complete_todo`, and `list_todos` tools available by name,
**so that** I can express and track my execution plan as structured tool calls rather
than unstructured prose.

### Implementation

**New file:** `shared_skills/planning/tools.py`

```python
import json
from shared_skills.planning import AgentTodoTracker
from shared_skills.tools import Tool


def make_planning_tools(tracker: AgentTodoTracker) -> list[Tool]:
    def write_todos(descriptions_json: str) -> str:
        try:
            items = json.loads(descriptions_json)
            assert isinstance(items, list)
        except Exception:
            return "ERROR: descriptions_json must be a JSON array of strings"
        tracker.write_todos(items)
        return f"Todo list updated with {len(items)} items.\n" + tracker.summary()

    def complete_todo(item_id: str, notes: str = "") -> str:
        try:
            tracker.complete_todo(item_id, notes)
            return f"Marked [{item_id}] done.\n" + tracker.summary()
        except KeyError:
            return f"ERROR: no todo with id {item_id!r}"

    def list_todos() -> str:
        return tracker.summary()

    return [
        Tool(
            name="write_todos",
            description=(
                "Set your task plan. Pass a JSON array of step descriptions. "
                "Call this at the start of your work before taking any other actions."
            ),
            parameters={"descriptions_json": "str — JSON array of step descriptions"},
            fn=write_todos,
        ),
        Tool(
            name="complete_todo",
            description="Mark a todo item as done. Pass the item id from list_todos.",
            parameters={"item_id": "str", "notes": "str (optional)"},
            fn=complete_todo,
        ),
        Tool(
            name="list_todos",
            description="Show the current todo list with status markers.",
            parameters={},
            fn=list_todos,
        ),
    ]
```

**Acceptance criteria:**
- `write_todos` with a non-JSON string returns an `ERROR:` string, does not raise.
- `complete_todo` with an unknown id returns an `ERROR:` string, does not raise.
- `list_todos` returns the same content as `tracker.summary()`.

**Tests:** `tests/test_planning.py`
```python
def test_write_todos_tool_parses_json_array():
    tracker = AgentTodoTracker()
    tools = {t.name: t for t in make_planning_tools(tracker)}
    result = tools["write_todos"].fn('["step 1", "step 2"]')
    assert "[  ]" in result or "[ ]" in result
    assert len(tracker.pending()) == 2

def test_complete_todo_tool_unknown_id():
    tracker = AgentTodoTracker()
    tools = {t.name: t for t in make_planning_tools(tracker)}
    result = tools["complete_todo"].fn("bad-id")
    assert "ERROR" in result
```

---

## User Story 12.3 — Planning events in `EventRecorder`

**As a** platform operator,
**I want** planning actions (`write_todos`, `complete_todo`) emitted as events,
**so that** I can trace the agent's execution plan in the event log alongside
board lifecycle events.

### Implementation

**File:** `shared_skills/events/__init__.py`

Add constants:
```python
AGENT_PLAN_WRITTEN    = "agent_plan_written"
AGENT_TODO_STARTED    = "agent_todo_started"
AGENT_TODO_COMPLETED  = "agent_todo_completed"
AGENT_TODO_SKIPPED    = "agent_todo_skipped"
```

**File:** `shared_skills/planning/__init__.py`

`AgentTodoTracker` accepts an optional `events: EventRecorder` at construction.
On `write_todos`, emit `AGENT_PLAN_WRITTEN` with `{"count": len(descriptions)}`.
On `complete_todo`, emit `AGENT_TODO_COMPLETED` with `{"id": ..., "notes": ...}`.

**Acceptance criteria:**
- `EventRecorder.events` contains one `agent_plan_written` event per `write_todos` call.
- `agent_todo_completed` is emitted with the correct item id.

**Tests:** `tests/test_planning.py`
```python
def test_planning_events_emitted():
    events = EventRecorder()
    tracker = AgentTodoTracker(events=events)
    tracker.write_todos(["step 1"])
    tracker.complete_todo(tracker.pending()[0].id)
    types = [e["type"] for e in events.events]
    assert "agent_plan_written" in types
    assert "agent_todo_completed" in types
```

---

## User Story 12.4 — `BoardAgent` injects `AgentTodoTracker` into TAO loop

**As a** board agent,
**I want** the TAO loop (Sprint 7) to automatically include `write_todos`,
`complete_todo`, and `list_todos` in every agent's tool registry,
**so that** all agents can plan without any per-agent boilerplate.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

In the TAO loop setup (Sprint 7's `_run_tao_loop`), always register planning tools:

```python
from shared_skills.planning import AgentTodoTracker
from shared_skills.planning.tools import make_planning_tools

self._todo_tracker = AgentTodoTracker(events=self.events)
for tool in make_planning_tools(self._todo_tracker):
    self._tool_registry.register(tool)
```

Expose the tracker as `self.todo_tracker` for testing.

**Acceptance criteria:**
- Every concrete agent class has access to `self.todo_tracker` without extra configuration.
- The harness end-to-end test passes with planning tools registered.
- No regression in any existing test.

**Tests:** `tests/test_planning.py`
```python
def test_board_agent_exposes_todo_tracker(monkeypatch):
    agent = DataArchitectAgent(ado=board, teams=teams, approvals=approvals,
                               config=config, llm=FallbackLLM())
    assert hasattr(agent, "todo_tracker")
    assert isinstance(agent.todo_tracker, AgentTodoTracker)
```
