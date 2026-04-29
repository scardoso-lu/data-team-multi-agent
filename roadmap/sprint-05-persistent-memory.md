# Sprint 5 — Persistent Cross-Session Memory

## Gap
Every agent run starts cold. There is no cross-session memory store, no mechanism for
an agent to remember patterns from previous work items, and no equivalent of the
`AGENTS.md` memory file that LangChain harnesses load on startup and update over time.
Agents repeat the same LLM prompts regardless of what worked or failed in prior runs.

## Goal
Introduce a file-backed `AgentMemoryStore`. Each agent loads its memory at startup,
injects a summary into every LLM prompt via a `MemoryMiddleware`, and writes new
insights back after processing each work item.

---

## User Story 5.1 — `AgentMemoryStore` with file-backed persistence

**As a** board agent,
**I want** a structured store that persists key/value insights across process restarts,
**so that** I can accumulate knowledge about recurring patterns, blockers, and fixes.

### Implementation

**New file:** `shared_skills/memory/__init__.py`

```python
import json
import os
from pathlib import Path
from threading import Lock
from time import time


class AgentMemoryStore:
    """File-backed per-agent key/value memory store."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = Lock()
        self._data = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def read(self):
        with self._lock:
            return dict(self._data)

    def update(self, key, value):
        with self._lock:
            self._data[key] = {"value": value, "updated_at": time()}
            self._save()

    def forget(self, key):
        with self._lock:
            self._data.pop(key, None)
            self._save()

    def summary(self, max_entries=10):
        """Return a compact text block suitable for LLM prompt injection."""
        with self._lock:
            if not self._data:
                return ""
            entries = sorted(
                self._data.items(),
                key=lambda kv: kv[1].get("updated_at", 0),
                reverse=True,
            )[:max_entries]
        lines = ["Agent memory (most recent):"]
        for key, record in entries:
            lines.append(f"  - {key}: {record['value']}")
        return "\n".join(lines)
```

**Memory file location** (convention, not enforced):
`logs/memory/{agent_key}/memory.json`

**Acceptance criteria:**
- `update(key, value)` persists to disk; a new `AgentMemoryStore` on the same path
  reads it back.
- `forget(key)` removes the key and persists.
- `summary()` returns a non-empty string when entries exist, empty string when not.
- Concurrent `update` calls from multiple threads do not corrupt the file.

**Tests:** `tests/test_memory.py` (new file)
- Write a value, reload the store from disk, assert value is present.
- Call `forget`, reload, assert key is absent.
- Assert `summary()` returns empty string for a fresh store.
- Assert `summary()` lists entries newest-first.

---

## User Story 5.2 — `MemoryMiddleware` injects memory into every LLM prompt

**As a** board agent,
**I want** my accumulated memory injected into every LLM prompt via `before_model`,
**so that** the model can apply prior knowledge when processing new work items.

### Implementation

**New file:** `shared_skills/middleware/memory.py`

```python
from shared_skills.middleware import BaseMiddleware


class MemoryMiddleware(BaseMiddleware):
    def __init__(self, memory_store):
        self.store = memory_store

    def before_model(self, prompt, context):
        summary = self.store.summary()
        if not summary:
            return prompt
        return f"{summary}\n\n{prompt}"
```

Wire in each agent's `__init__`:
```python
from memory import AgentMemoryStore
from middleware.memory import MemoryMiddleware

memory_path = f"logs/memory/{self.agent_key}/memory.json"
self.memory = AgentMemoryStore(memory_path)
memory_mw = MemoryMiddleware(self.memory)
# prepend to middlewares list so memory loads before PII scrubbing
```

**Acceptance criteria:**
- When the memory store contains entries, the LLM prompt starts with
  `"Agent memory (most recent):"`.
- When the memory store is empty, the prompt is unchanged.

**Tests:** `tests/test_middleware.py`
- Populate a memory store with two entries.
- Run `MemoryMiddleware.before_model` on a plain prompt.
- Assert the returned prompt starts with `"Agent memory"`.
- Assert both entries appear in the injected text.

---

## User Story 5.3 — Agents write insights to memory after each work item

**As a** board agent,
**I want** to record a short insight after processing each work item,
**so that** future runs benefit from accumulated operational knowledge.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

Add a `record_memory` template method to `BoardAgent`:
```python
def record_memory(self, work_item_id, artifact, result_status):
    """Override in concrete agents to write insights to self.memory."""
    pass
```

Call it in `process_next_item` just before returning the success result:
```python
if hasattr(self, "memory"):
    self.record_memory(work_item_id, artifact, "processed")
return {"agent": ..., "status": "processed", ...}
```

Example override in `DataArchitectAgent`:
```python
def record_memory(self, work_item_id, artifact, result_status):
    story_count = len(artifact.get("user_stories", []))
    self.memory.update(
        f"work_item_{work_item_id}_stories",
        f"Generated {story_count} user stories with status={result_status}",
    )
    table_count = len(artifact.get("tables", []))
    self.memory.update("last_table_count", str(table_count))
```

**Acceptance criteria:**
- After a successful `process_next_item`, the memory file contains at least one new entry.
- `record_memory` is a no-op in the base class (no crash if `self.memory` is absent).

**Tests:** `tests/test_data_architect.py`
- After `process_next_item` on a valid work item, read the memory file and assert at
  least one key is present.

---

## User Story 5.4 — Memory is not written when the work item is blocked or fails

**As a** board agent,
**I want** memory to remain clean when a work item is blocked or fails,
**so that** incorrect or incomplete insights are not persisted.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

Only call `record_memory` on the `"processed"` path. Do **not** call it in the
`WorkItemBlocked` handler or the `failure_result` handler.

**Acceptance criteria:**
- A `WorkItemBlocked` exception leaves the memory file unchanged.
- A failure (exception in `execute_stage`) leaves the memory file unchanged.

**Tests:** `tests/test_memory.py`
- Inject an `execute_stage` that raises `WorkItemBlocked`.
- After `process_next_item`, assert the memory store has no new entries.
