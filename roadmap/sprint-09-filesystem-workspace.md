# Sprint 9 — Agent Filesystem Workspace

## Gap

LangChain's harness anatomy identifies the filesystem as *"arguably the most
foundational harness primitive."* An agent with a persistent workspace can
incrementally read, write, and search files — offloading context rather than
keeping every intermediate result in the LLM's context window.

Currently every intermediate result lives only in memory as a Python dict.
There are no file-backed tools exposed to the LLM, no per-agent working
directory, and no way to reference an artifact produced in a previous step
by filename rather than by re-embedding the whole dict into the next prompt.

## Goal

Give every agent a dedicated working directory (`workspaces/<agent_key>/`).
Expose five file tools to the LLM via the `ToolRegistry` introduced in Sprint 7:
`read_file`, `write_file`, `list_files`, `grep_files`, and `delete_file`.
Allow artifact serialisation to write a JSON sidecar to the workspace so that
downstream agents can load it by reference instead of receiving the full payload.

---

## User Story 9.1 — `WorkspaceManager` with per-agent directories

**As a** board agent,
**I want** a managed working directory scoped to my `agent_key`,
**so that** I can write and read files without colliding with other agents or runs.

### Implementation

**New file:** `shared_skills/workspace/__init__.py`

```python
import json
import shutil
from pathlib import Path


class WorkspaceManager:
    def __init__(self, base_dir: str, agent_key: str, work_item_id: str):
        self.root = Path(base_dir) / agent_key / work_item_id
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, filename: str) -> Path:
        return self.root / filename

    def write_json(self, filename: str, data: dict) -> Path:
        p = self.path(filename)
        p.write_text(json.dumps(data, indent=2))
        return p

    def read_json(self, filename: str) -> dict:
        return json.loads(self.path(filename).read_text())

    def exists(self, filename: str) -> bool:
        return self.path(filename).exists()

    def list_files(self) -> list[str]:
        return [f.name for f in self.root.iterdir() if f.is_file()]

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)
```

**Acceptance criteria:**
- `WorkspaceManager("workspaces", "data_architect", "wi-1").root` resolves to
  `workspaces/data_architect/wi-1/`.
- `write_json` / `read_json` round-trip correctly.
- `list_files` returns only files, not subdirectories.

**Tests:** `tests/test_workspace.py`
```python
def test_workspace_roundtrip(tmp_path):
    ws = WorkspaceManager(str(tmp_path), "data_architect", "wi-1")
    ws.write_json("artifact.json", {"tables": []})
    assert ws.read_json("artifact.json") == {"tables": []}
    assert "artifact.json" in ws.list_files()
```

---

## User Story 9.2 — Five file tools registered in `ToolRegistry`

**As an** LLM running inside a TAO loop (Sprint 7),
**I want** `read_file`, `write_file`, `list_files`, `grep_files`, and `delete_file`
tools available in the registry,
**so that** I can incrementally build and query a workspace without holding
everything in my context window.

### Implementation

**New file:** `shared_skills/workspace/tools.py`

```python
import re
from shared_skills.workspace import WorkspaceManager
from shared_skills.tools import Tool


def make_file_tools(ws: WorkspaceManager) -> list[Tool]:
    def read_file(filename: str) -> str:
        if not ws.exists(filename):
            return f"ERROR: {filename} not found"
        return ws.path(filename).read_text()

    def write_file(filename: str, content: str) -> str:
        ws.path(filename).write_text(content)
        return f"Written {len(content)} bytes to {filename}"

    def list_files() -> str:
        files = ws.list_files()
        return "\n".join(files) if files else "(empty workspace)"

    def grep_files(pattern: str, filename: str = "") -> str:
        targets = [ws.path(filename)] if filename else [ws.path(f) for f in ws.list_files()]
        matches = []
        rx = re.compile(pattern)
        for p in targets:
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if rx.search(line):
                    matches.append(f"{p.name}:{i}: {line}")
        return "\n".join(matches) if matches else "(no matches)"

    def delete_file(filename: str) -> str:
        p = ws.path(filename)
        if p.exists():
            p.unlink()
            return f"Deleted {filename}"
        return f"ERROR: {filename} not found"

    return [
        Tool(name="read_file", description="Read a file from the workspace",
             parameters={"filename": "str"}, fn=read_file),
        Tool(name="write_file", description="Write content to a file in the workspace",
             parameters={"filename": "str", "content": "str"}, fn=write_file),
        Tool(name="list_files", description="List all files in the workspace",
             parameters={}, fn=list_files),
        Tool(name="grep_files", description="Search files by regex pattern",
             parameters={"pattern": "str", "filename": "str (optional)"}, fn=grep_files),
        Tool(name="delete_file", description="Delete a file from the workspace",
             parameters={"filename": "str"}, fn=delete_file),
    ]
```

**Acceptance criteria:**
- All five tools are instantiable and callable without errors.
- `grep_files` returns matching lines with `filename:lineno:` prefix.
- Tools registered in a `ToolRegistry` (Sprint 7) are discoverable by name.

**Tests:** `tests/test_workspace_tools.py`
```python
def test_write_then_grep(tmp_path):
    ws = WorkspaceManager(str(tmp_path), "qa_engineer", "wi-2")
    tools = {t.name: t for t in make_file_tools(ws)}
    tools["write_file"].fn("schema.sql", "CREATE TABLE orders (id INT);\n")
    result = tools["grep_files"].fn("CREATE TABLE")
    assert "schema.sql:1:" in result
```

---

## User Story 9.3 — Agents create a workspace per work item and write artifact sidecars

**As a** `BoardAgent`,
**I want** a workspace created when I claim a work item and the final artifact
written as a JSON sidecar (`artifact.json`),
**so that** downstream agents or debugging tools can load the artifact from disk
without the upstream agent needing to embed the full payload in every handoff.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

In `process_next_item`, after `execute_stage` succeeds:
```python
from shared_skills.workspace import WorkspaceManager

ws = WorkspaceManager(
    base_dir=self.config.require("runtime", "workspace_dir"),
    agent_key=self.agent_key,
    work_item_id=work_item_id,
)
ws.write_json("artifact.json", artifact)
self._workspace = ws   # expose for execute_stage access via self.workspace
```

**File:** `config/default.json`
```json
"runtime": {
  ...
  "workspace_dir": "workspaces"
}
```

**Acceptance criteria:**
- After `process_next_item` succeeds, `workspaces/<agent_key>/<work_item_id>/artifact.json`
  exists and round-trips to the returned artifact.
- `self.workspace` is available inside `execute_stage` so agents can call
  `self.workspace.write_json(...)` for intermediate files.

**Tests:** `tests/test_workspace_integration.py`
```python
def test_agent_writes_artifact_sidecar(tmp_path, monkeypatch):
    # Use DataArchitectAgent with FakeBoardClient; assert sidecar written
    ...
```

---

## User Story 9.4 — `WorkspaceManager` cleanup after terminal stage

**As a** platform operator,
**I want** workspaces to be cleaned up when a work item reaches the terminal column,
**so that** disk usage does not grow unboundedly in long-running deployments.

### Implementation

**File:** `shared_skills/agent_base/__init__.py`

In `DataStewardAgent.execute_stage` (terminal agent), after writing the final
artifact, iterate over all known agent keys and call `WorkspaceManager.cleanup()`:

```python
def _cleanup_workspaces(self, work_item_id: str):
    from shared_skills.workspace import WorkspaceManager
    for key in ["requirements_analyst", "data_architect", "data_engineer",
                "qa_engineer", "data_analyst", "data_steward"]:
        WorkspaceManager(
            self.config.require("runtime", "workspace_dir"), key, work_item_id
        ).cleanup()
```

**Acceptance criteria:**
- After the terminal agent processes an item, the `workspaces/` subtree for
  that `work_item_id` no longer exists.
- Cleanup failure (already-missing directory) is silently ignored.

**Tests:** `tests/test_workspace_integration.py`
```python
def test_terminal_agent_cleans_up_workspace(tmp_path):
    ...
    assert not (tmp_path / "data_steward" / work_item_id).exists()
```
