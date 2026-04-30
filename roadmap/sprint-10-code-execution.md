# Sprint 10 — Code & Command Execution Tool

## Gap

LangChain's harness anatomy lists an `execute` tool (sandboxed shell/code runner) as
a core primitive alongside filesystem tools. Agents in this project currently produce
artifacts entirely via LLM inference — they cannot run a SQL linter, execute a Python
snippet to verify a calculation, or invoke a CLI tool to validate a schema.

The most acute pain point is the `QAEngineerAgent`: its quality checks are described
in a JSON artifact but never *run*. The check results are plausible-sounding LLM
outputs, not the output of actual validation logic.

## Goal

Add a `CodeExecutor` tool that runs Python snippets and shell commands in a
subprocess sandbox with a configurable timeout. Register it in the `ToolRegistry`
(Sprint 7) so the LLM can request code execution as a TAO action. Surface
`stdout`, `stderr`, and exit code as the observation. Never allow writes outside
the agent's workspace (Sprint 9).

---

## User Story 10.1 — `CodeExecutor` with subprocess sandbox

**As a** board agent running a TAO loop,
**I want** to execute short Python snippets or shell commands in a sandboxed
subprocess,
**so that** I can validate schema SQL, run a calculation, or invoke a CLI tool
and receive the real output as a TAO observation.

### Implementation

**New file:** `shared_skills/code_executor/__init__.py`

```python
import subprocess
import sys
import textwrap
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    def as_observation(self) -> str:
        parts = []
        if self.timed_out:
            parts.append("TIMEOUT: execution exceeded time limit")
        if self.stdout:
            parts.append(f"stdout:\n{self.stdout}")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr}")
        parts.append(f"exit_code: {self.exit_code}")
        return "\n".join(parts)


class CodeExecutor:
    def __init__(self, timeout_seconds: int = 10, allowed_cwd: str = "."):
        self.timeout = timeout_seconds
        self.allowed_cwd = allowed_cwd

    def run_python(self, code: str) -> ExecutionResult:
        dedented = textwrap.dedent(code)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", dedented],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.allowed_cwd,
            )
            return ExecutionResult(
                stdout=proc.stdout[:4096],
                stderr=proc.stderr[:4096],
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)

    def run_shell(self, command: str) -> ExecutionResult:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.allowed_cwd,
            )
            return ExecutionResult(
                stdout=proc.stdout[:4096],
                stderr=proc.stderr[:4096],
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)
```

**Acceptance criteria:**
- `run_python("print(1 + 1)")` returns `ExecutionResult(stdout="2\n", exit_code=0)`.
- `run_python` with an infinite loop returns `ExecutionResult(timed_out=True)` within
  `timeout + 1` seconds.
- `run_shell("echo hello")` returns `stdout="hello\n"`.
- Output is truncated at 4096 characters to protect context window.

**Tests:** `tests/test_code_executor.py`
```python
def test_run_python_basic():
    result = CodeExecutor().run_python("print(2 ** 10)")
    assert result.stdout.strip() == "1024"
    assert result.exit_code == 0

def test_run_python_timeout():
    result = CodeExecutor(timeout_seconds=1).run_python("while True: pass")
    assert result.timed_out is True

def test_run_python_syntax_error():
    result = CodeExecutor().run_python("def (:")
    assert result.exit_code != 0
    assert "SyntaxError" in result.stderr
```

---

## User Story 10.2 — `execute_python` and `execute_shell` tools for `ToolRegistry`

**As an** LLM running inside a TAO loop,
**I want** `execute_python` and `execute_shell` registered as named tools,
**so that** I can call them by name in a tool-use JSON response and receive
the output as my next observation.

### Implementation

**New file:** `shared_skills/code_executor/tools.py`

```python
from shared_skills.code_executor import CodeExecutor
from shared_skills.tools import Tool


def make_executor_tools(executor: CodeExecutor) -> list[Tool]:
    return [
        Tool(
            name="execute_python",
            description=(
                "Run a Python snippet. Returns stdout, stderr, and exit_code. "
                "Use for calculations, schema validation, or data checks. "
                "Do not write files outside the workspace."
            ),
            parameters={"code": "str — the Python code to execute"},
            fn=lambda code: executor.run_python(code).as_observation(),
        ),
        Tool(
            name="execute_shell",
            description=(
                "Run a shell command. Returns stdout, stderr, and exit_code. "
                "Use for CLI tools (e.g. sqlfluff, yamllint). "
                "Do not write files outside the workspace."
            ),
            parameters={"command": "str — the shell command to run"},
            fn=lambda command: executor.run_shell(command).as_observation(),
        ),
    ]
```

**Acceptance criteria:**
- Both tools are callable via `tool.fn(...)` and return a string observation.
- The `description` field is populated so the LLM prompt builder (Sprint 7)
  includes them in the tool list section of the system prompt.

**Tests:** `tests/test_code_executor.py`
```python
def test_execute_python_tool_returns_observation():
    executor = CodeExecutor()
    tools = {t.name: t for t in make_executor_tools(executor)}
    obs = tools["execute_python"].fn("print('ok')")
    assert "stdout" in obs
    assert "ok" in obs
```

---

## User Story 10.3 — `QAEngineerAgent` runs Python validation checks

**As a** QA Engineer agent,
**I want** to execute a Python snippet for each check type (schema, completeness,
uniqueness) against the fabric artifact,
**so that** the quality artifact reflects checks that actually ran rather than
checks the LLM invented.

### Implementation

**File:** `agents/qa_engineer/app.py`

In `execute_stage`, after loading the upstream artifact, build a validation
snippet per pipeline and run it with `CodeExecutor`:

```python
def _run_check(self, pipeline_name: str, check_type: str, snippet: str) -> dict:
    result = self._executor.run_python(snippet)
    return {
        "status": "passed" if result.exit_code == 0 else "failed",
        "issues": result.stderr.splitlines() if result.exit_code != 0 else [],
        "executed": True,
    }
```

The LLM is still consulted to generate the check snippets; the executor runs them.
Fallback (when no LLM is available) retains the existing static check dict so the
harness remains deterministic.

**Acceptance criteria:**
- When a snippet exits 0, the check status is `"passed"`.
- When a snippet exits non-zero, `issues` contains the stderr lines.
- `"executed": True` distinguishes real execution from LLM-generated fallbacks.
- The harness test suite continues to pass (fallback path unchanged).

**Tests:** `tests/test_qa_engineer.py`
```python
def test_qa_engineer_marks_check_executed(monkeypatch):
    # Provide a snippet that always exits 0; assert executed=True, status=passed
    ...
```

---

## User Story 10.4 — `allowed_cwd` sandbox enforcement

**As a** security-conscious platform operator,
**I want** the `CodeExecutor` to be restricted to the agent's workspace directory,
**so that** LLM-generated code cannot read or write files outside the workspace.

### Implementation

**File:** `shared_skills/code_executor/__init__.py`

- `CodeExecutor` always receives `allowed_cwd` from the `WorkspaceManager.root`
  (Sprint 9).
- Subprocess `cwd` is set to `allowed_cwd`.
- Add a guard: reject commands containing `..` path traversal patterns.

```python
_TRAVERSAL = re.compile(r"\.\.[/\\]")

def _check_command(self, cmd: str):
    if _TRAVERSAL.search(cmd):
        raise ValueError(f"Path traversal detected in command: {cmd!r}")
```

**Acceptance criteria:**
- `run_python` with a `..` in a file path raises `ValueError`.
- Subprocess `cwd` matches the workspace root.
- `run_shell("pwd")` returns a path inside the workspace directory.

**Tests:** `tests/test_code_executor.py`
```python
def test_traversal_rejected():
    with pytest.raises(ValueError, match="traversal"):
        CodeExecutor().run_shell("cat ../../etc/passwd")
```
