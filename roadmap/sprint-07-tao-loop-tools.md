# Sprint 7 — Iterative TAO Loop & Tool Calling

## Gap

### No iterative loop (TAO/ReAct)
Each agent calls the LLM exactly once per work item (`complete_json`), then stops.
There is no Thought → Action → Observation → repeat cycle. The model gets one shot
and Python acts on the JSON blob. Complex tasks requiring mid-task replanning,
multi-step reasoning, or conditional tool use cannot be expressed.

### LLM cannot call tools
The LLM produces JSON that Python code interprets. There is no tool schema injection
into the LLM context, no tool dispatch from the LLM, and no observation fed back.
The model is used purely as a JSON-to-JSON transformer.

## Goal
Replace the single `complete_json` call inside `execute_stage` with an iterative TAO
loop. Define a `Tool` interface and a `ToolRegistry`. Let the LLM request tool
calls by name; dispatch them and append observations to the conversation; repeat until
the model signals `done` or the step limit is reached.

---

## User Story 7.1 — `Tool` interface and `ToolRegistry`

**As a** board agent,
**I want** a standard interface for defining callable tools,
**so that** tools can be registered, described to the LLM, and dispatched uniformly.

### Implementation

**New file:** `shared_skills/tools/__init__.py`

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]   # JSON Schema object for the arguments dict
    execute: Callable[[Dict[str, Any]], str]   # returns an observation string

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def schema_list(self) -> List[Dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def dispatch(self, name: str, args: Dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        try:
            return self._tools[name].execute(args)
        except Exception as exc:
            return f"Error executing tool '{name}': {exc}"
```

**File:** `shared_skills/agent_base/__init__.py`

Add to `BoardAgent.__init__`:
```python
from tools import ToolRegistry
self.tools = ToolRegistry()
self._register_default_tools()
```

Add:
```python
def _register_default_tools(self):
    """Override in concrete agents to register role-specific tools."""
    pass
```

**Acceptance criteria:**
- `ToolRegistry.dispatch` returns the tool's output string on success.
- `ToolRegistry.dispatch` returns an error string for unknown tool names.
- `ToolRegistry.schema_list` returns one schema dict per registered tool.

**Tests:** `tests/test_tools.py` (new file)
- Register a tool that returns `"pong"` for any input.
- Assert `dispatch("ping", {})` returns `"pong"`.
- Assert `dispatch("missing", {})` returns an error string.
- Assert `schema_list()` contains the tool's name and description.

---

## User Story 7.2 — TAO loop runner in `LocalLLMClient`

**As a** board agent,
**I want** the LLM client to support an iterative loop where the model can request
tool calls and receive observations before producing a final result,
**so that** agents are no longer limited to single-shot reasoning.

### Implementation

**File:** `shared_skills/llm_integration/__init__.py`

Add `run_tao_loop`:

```python
def run_tao_loop(
    self,
    task: str,
    payload: dict,
    tool_registry,
    fallback=None,
    max_steps: int = 6,
):
    """
    Run a Thought-Action-Observation loop.

    The LLM must return one of two JSON shapes each step:
      {"thought": "...", "tool_call": {"name": "...", "args": {...}}}
      {"thought": "...", "result": <final artifact dict>}

    On "tool_call" the tool is dispatched and the observation is appended to
    the conversation history for the next step. On "result" the loop exits.
    """
    history = []
    tool_schemas = tool_registry.schema_list() if tool_registry else []

    for step in range(max_steps):
        step_payload = {
            "original_payload": payload,
            "conversation_history": history,
            "available_tools": tool_schemas,
            "step": step,
            "instruction": (
                "Either call a tool using {\"tool_call\": {\"name\": ..., \"args\": ...}} "
                "or return the final artifact using {\"result\": {...}}."
            ),
        }
        response = self.complete_json(task, step_payload, fallback=None)

        if not isinstance(response, dict):
            break   # non-JSON response — exit loop and use fallback

        if "result" in response:
            return response["result"]   # done

        if "tool_call" in response:
            tool_call = response["tool_call"]
            name = tool_call.get("name", "")
            args = tool_call.get("args", {})
            observation = tool_registry.dispatch(name, args) if tool_registry else "No tools available"
            history.append({
                "step": step,
                "thought": response.get("thought", ""),
                "tool_call": tool_call,
                "observation": observation,
            })
            continue

        # Unexpected shape — treat as final result
        return response

    return fallback
```

**Acceptance criteria:**
- When the LLM returns `{"result": {...}}`, the loop exits and returns the result.
- When the LLM returns `{"tool_call": {...}}`, the tool is dispatched and the loop continues.
- After `max_steps` without a `result`, `fallback` is returned.

**Tests:** `tests/test_llm_integration.py`
- Stub `_run_first_available` to return a `tool_call` on step 0 and a `result` on step 1.
- Assert the tool was dispatched once and the final result is returned.
- Stub to always return `tool_call`; assert fallback is returned after `max_steps`.

---

## User Story 7.3 — Built-in tools for `BoardAgent`

**As a** board agent,
**I want** standard tools for fetching work item details, posting comments, and
reading previously stored artifacts,
**so that** the LLM can look up live data mid-reasoning without Python hardcoding it.

### Implementation

**New file:** `shared_skills/tools/board_tools.py`

```python
import json
from tools import Tool


def make_get_work_item_details_tool(ado):
    def execute(args):
        work_item_id = args.get("work_item_id")
        details = ado.get_work_item_details(work_item_id)
        return json.dumps(details, default=str)

    return Tool(
        name="get_work_item_details",
        description="Fetch full details of an ADO work item by ID.",
        parameters={
            "type": "object",
            "properties": {
                "work_item_id": {"type": "string", "description": "ADO work item ID"}
            },
            "required": ["work_item_id"],
        },
        execute=execute,
    )


def make_post_comment_tool(teams, work_item_id):
    def execute(args):
        message = args.get("message", "")
        teams.send_notification(
            title=args.get("title", "Agent comment"),
            message=message,
            work_item_id=work_item_id,
        )
        return "Comment posted."

    return Tool(
        name="post_comment",
        description="Post a comment or status update to the ADO work item discussion.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
        execute=execute,
    )


def make_read_artifact_tool(ado):
    def execute(args):
        work_item_id = args.get("work_item_id")
        artifact = ado.get_work_item_details(work_item_id)
        return json.dumps(artifact, default=str)

    return Tool(
        name="read_artifact",
        description="Read the artifact stored on a work item by a previous pipeline stage.",
        parameters={
            "type": "object",
            "properties": {
                "work_item_id": {"type": "string"}
            },
            "required": ["work_item_id"],
        },
        execute=execute,
    )
```

Register default tools in `BoardAgent._register_default_tools`:

```python
from tools.board_tools import (
    make_get_work_item_details_tool,
    make_post_comment_tool,
    make_read_artifact_tool,
)

def _register_default_tools(self):
    self.tools.register(make_get_work_item_details_tool(self.ado))
    self.tools.register(make_read_artifact_tool(self.ado))
    # post_comment is registered after self.work_item_id is set, inside execute_stage
```

**Acceptance criteria:**
- `get_work_item_details` returns JSON-serialised details from `ado`.
- `post_comment` calls `teams.send_notification`.
- `read_artifact` returns JSON-serialised artifact dict.
- All three tools are registered on `BoardAgent.tools` by default.

**Tests:** `tests/test_tools.py`
- Inject `FakeBoardClient` and `FakeNotificationClient`.
- Dispatch `get_work_item_details` and assert the result is valid JSON.
- Dispatch `post_comment` and assert `FakeNotificationClient.notifications` grew by one.

---

## User Story 7.4 — Replace single `complete_json` with `run_tao_loop` in `DataArchitectAgent`

**As a** data architect agent,
**I want** to use the TAO loop for architecture design,
**so that** I can look up live work item data, request clarifying information, and
iterate on my design before committing to a final architecture artifact.

### Implementation

**File:** `agents/data_architect/app.py`

Replace in `design_architecture`:
```python
# Before:
architecture_doc = self.llm.complete_json(
    task=load_task("data_architect"),
    payload={"requirements": requirements, "fallback_contract": fallback},
    fallback=fallback,
)

# After:
self.tools.register(make_post_comment_tool(self.teams, self.work_item_id))
architecture_doc = self.llm.run_tao_loop(
    task=load_task("data_architect"),
    payload={"requirements": requirements, "fallback_contract": fallback},
    tool_registry=self.tools,
    fallback=fallback,
    max_steps=self.runtime_config.get("tao_max_steps", 6),
)
```

**Config addition** (`config/default.json`, under `runtime`):
```json
"tao_max_steps": 6
```

When no LLM CLI is available `run_tao_loop` returns `fallback` directly (same offline
behaviour as before).

**Acceptance criteria:**
- With no CLI available, behaviour is identical to the current single-call path.
- With a CLI that returns a direct `result`, one step is used.
- With a CLI that calls `get_work_item_details` first, the tool is dispatched and the
  observation appears in step 1's `conversation_history`.
- All existing `tests/test_data_architect.py` tests pass without modification.

**Tests:** `tests/test_data_architect.py`
- Add a test where the stub LLM returns a `tool_call` on step 0 and a `result` on step 1.
- Assert the final artifact is the step-1 result.

---

## User Story 7.5 — Apply TAO loop to remaining four agents

**As a** pipeline operator,
**I want** all five agents using the TAO loop,
**so that** any agent can gather additional context mid-reasoning rather than being
limited to the payload provided at the start of `execute_stage`.

### Implementation

Apply the same pattern from US 7.4 to:

| Agent | Method to update |
|---|---|
| `DataEngineerAgent` | `implement_medallion_architecture` |
| `QAEngineerAgent` | `run_data_quality_checks` |
| `DataAnalystAgent` | `develop_semantic_model` |
| `DataStewardAgent` | `audit_lifecycle` |

Each agent:
1. Calls `self.tools.register(make_post_comment_tool(...))` before the loop.
2. Replaces `self.llm.complete_json(...)` with `self.llm.run_tao_loop(...)`.
3. Passes its `tool_registry=self.tools` and `fallback=<existing fallback>`.

**Acceptance criteria:**
- All five agents use `run_tao_loop` for their primary LLM call.
- All existing agent tests pass without modification (offline fallback path unchanged).
- New per-agent test verifies tool dispatch works in the TAO loop.


## Implementation Status

- [x] Sprint implementation completed in codebase
