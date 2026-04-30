# Sprint 4 — Checkpointing & Typed State Contracts

## Gap

### Checkpointing
If the agent process crashes between `claim_work_item` and `move_work_item`, the work
item is left claimed with no recovery. There is no in-progress marker, no timeout
detection, and no resumption path. Items silently stall.

### Typed State
Artifacts flowing between pipeline stages are plain untyped `dict`s. There is no typed
state contract (TypedDict or dataclass) enforced at boundaries. Shape is inferred from
`config/default.json` fallbacks and `validate_*` functions after the fact.

## Goal
Write a crash-safe checkpoint immediately after claiming a work item and clear it on
success. On startup, detect stale checkpoints and route them to the error column.
Introduce `TypedDict` definitions for all five artifact types so misshapen artifacts
are caught at definition time, not after the fact.

---

## User Story 4.1 — Write checkpoint on claim

**As a** board agent,
**I want** a checkpoint file written immediately after I claim a work item,
**so that** a process crash leaves a detectable trace for recovery.

### Implementation

**New file:** `shared_skills/checkpoint/__init__.py`

```python
import json
import os
from pathlib import Path
from time import time


def checkpoint_path(base_dir, agent_key, work_item_id):
    return Path(base_dir) / agent_key / f"{work_item_id}.json"


def write_checkpoint(base_dir, agent_key, work_item_id, stage="claimed"):
    path = checkpoint_path(base_dir, agent_key, work_item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "agent_key": agent_key,
                "work_item_id": work_item_id,
                "stage": stage,
                "claimed_at": time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def clear_checkpoint(base_dir, agent_key, work_item_id):
    path = checkpoint_path(base_dir, agent_key, work_item_id)
    path.unlink(missing_ok=True)


def list_stale_checkpoints(base_dir, agent_key, timeout_seconds):
    directory = Path(base_dir) / agent_key
    if not directory.exists():
        return []
    stale = []
    now = time()
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            age = now - record.get("claimed_at", now)
            if age > timeout_seconds:
                stale.append(record)
        except Exception:
            continue
    return stale
```

**File:** `shared_skills/agent_base/__init__.py`

Add to `BoardAgent.__init__`:
```python
self._checkpoint_dir = self.runtime_config.get("checkpoint_dir", "logs/checkpoints")
```

Update `process_next_item` — after `self.claim_work_item(work_item_id)`:
```python
write_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
```

After `self.move_to_next_column()` (success path):
```python
clear_checkpoint(self._checkpoint_dir, self.agent_key, work_item_id)
```

Also clear in the `WorkItemBlocked` and failure exception handlers.

**Config addition** (`config/default.json`, under `runtime`):
```json
"checkpoint_dir": "logs/checkpoints",
"claim_timeout_seconds": 1800
```

**Acceptance criteria:**
- `logs/checkpoints/{agent_key}/{work_item_id}.json` exists after claim.
- The file is removed after a successful `move_to_next_column`.
- The file is removed after a `WorkItemBlocked` skip or failure.
- The file contains `agent_key`, `work_item_id`, `stage`, and `claimed_at`.

**Tests:** `tests/test_checkpointing.py` (new file)
- After `process_next_item` succeeds, assert the checkpoint file is gone.
- Simulate a crash (don't call `clear_checkpoint`) and assert the file persists.

---

## User Story 4.2 — Detect and report stale checkpoints on startup

**As a** platform operator,
**I want** the agent to log a warning for any stale checkpoint older than the configured
timeout on startup,
**so that** stuck work items are surfaced immediately rather than silently waiting.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

Add a `_warn_stale_checkpoints` call at the end of `BoardAgent.__init__`:
```python
def _warn_stale_checkpoints(self, logger):
    timeout = self.runtime_config.get("claim_timeout_seconds", 1800)
    stale = list_stale_checkpoints(self._checkpoint_dir, self.agent_key, timeout)
    for record in stale:
        logger.warning(
            "Stale checkpoint detected: work_item_id=%s claimed_at=%s. "
            "The item may be stuck. Investigate and clear %s manually or "
            "move it to the error column.",
            record["work_item_id"],
            record["claimed_at"],
            checkpoint_path(self._checkpoint_dir, self.agent_key, record["work_item_id"]),
        )
```

Call from each agent's `run()` method, passing its logger:
```python
def run(self):
    self._warn_stale_checkpoints(logger)
    super().run(logger)
```

**Acceptance criteria:**
- A checkpoint older than `claim_timeout_seconds` triggers a `WARNING` log on startup.
- A fresh checkpoint (younger than the timeout) does not trigger a warning.

**Tests:** `tests/test_checkpointing.py`
- Write a checkpoint with `claimed_at = time() - (timeout + 1)`.
- Assert the warning is logged.

---

## User Story 4.3 — `TypedDict` schemas for all artifact types

**As a** developer,
**I want** typed definitions for each pipeline artifact,
**so that** editors can catch missing keys at write time, not after `validate_*` raises
at runtime.

### Implementation

**New file:** `shared_skills/artifact_types/__init__.py`

```python
from typing import Any, Dict, List, Literal, TypedDict


class AcceptanceCriterion(TypedDict):
    done: Literal["", "X"]
    item: str


class BusinessIOExample(TypedDict):
    input: Dict[str, Any]
    expected_output: Dict[str, Any]


class UserStory(TypedDict):
    title: str
    user_story: str
    specification: str
    acceptance_criteria: List[AcceptanceCriterion]
    business_io_examples: List[BusinessIOExample]


class ArchitectureArtifact(TypedDict):
    tables: List[str]
    relationships: Dict[str, Any]
    business_io_examples: List[BusinessIOExample]
    user_stories: List[UserStory]


class FabricArtifact(TypedDict):
    execution_mode: Literal["human_required"]
    proposed_workspace: str
    pipelines: List[str]
    business_io_examples: List[BusinessIOExample]
    user_stories: List[UserStory]


class PipelineQualityResult(TypedDict):
    status: str
    issues: List[Any]


class QualityArtifact(TypedDict):
    checks: Dict[str, PipelineQualityResult]
    business_io_examples: List[BusinessIOExample]


class SemanticModelTable(TypedDict):
    name: str
    columns: List[str]


class SemanticModelRelationship(TypedDict):
    from_: str   # "from" is a Python keyword — use from_ in code
    to: str


class SemanticModelArtifact(TypedDict):
    tables: List[SemanticModelTable]
    relationships: List[SemanticModelRelationship]
    business_io_examples: List[BusinessIOExample]


class GovernanceArtifact(TypedDict):
    architecture: str
    engineering: str
    qa: str
    analytics: str
    governance: str
```

**Acceptance criteria:**
- All types are importable: `from artifact_types import ArchitectureArtifact`.
- A `TypedDict` for every artifact type validated in `shared_skills/artifacts/__init__.py`.

**Tests:** `tests/test_artifact_types.py` (new file)
- Instantiate each `TypedDict` with valid data; assert no `TypeError`.
- Assert that a dict missing a required key is detectable via `typing.get_type_hints`.

---

## User Story 4.4 — Use typed schemas in `validate_*` functions

**As a** developer,
**I want** `validate_*` functions to accept and return typed artifacts,
**so that** callers get type-checked return values and IDEs can offer completions.

### Implementation

**File:** `shared_skills/artifacts/__init__.py`

Update each `validate_*` signature to add a return type annotation:

```python
from artifact_types import ArchitectureArtifact

def validate_architecture_artifact(artifact) -> ArchitectureArtifact:
    # existing validation body unchanged
    return artifact   # type: ignore[return-value]  — runtime is duck-typed
```

Apply the same annotation to `validate_fabric_artifact`, `validate_quality_artifact`,
`validate_semantic_model_artifact`, and `validate_governance_artifact`.

Update each concrete agent's `validate_artifact` signature:
```python
# DataArchitectAgent
def validate_artifact(self, artifact) -> ArchitectureArtifact:
    return validate_architecture_artifact(artifact)
```

**Acceptance criteria:**
- Return type annotations are present on all five `validate_*` functions.
- `mypy --strict` (or `pyright`) reports no new errors for `shared_skills/artifacts`.
- No runtime behaviour changes; all existing tests pass unchanged.

**Tests:** Existing `tests/test_artifacts.py` suite must pass without modification.


## Implementation Status

- [x] Sprint implementation completed in codebase
