from evaluation import build_scorecard
from feedback import append_feedback
from planning import rank_plan_steps
from planning import AgentTodoTracker
from planning.tools import (
    make_complete_todo_tool,
    make_list_todos_tool,
    make_rank_plan_steps_tool,
    make_write_todos_tool,
)
from policy import PolicyEngine, PolicyRule
from policy.packs import build_policy_rules
from release_gates import evaluate_release_gates
from replay import compare_traces, replay_events, save_trace
from workspace import WorkspaceManager
from code_executor import CodeExecutor
from code_executor.tools import make_execute_python_tool
from delegation import AgentTaskDispatcher
from delegation.tools import make_delegate_task_tool
from events import (
    AGENT_DELEGATION_COMPLETED,
    AGENT_DELEGATION_STARTED,
    AGENT_TODO_COMPLETED,
    AGENT_TODO_STARTED,
    ARTIFACT_CREATED,
    EventRecorder,
    MCP_TOOL_COMPLETED,
    MCP_TOOL_INVOKED,
    RELEASE_GATE_EVALUATED,
)
from llm_integration.provider_registry import ProviderRegistry
from mcp import MCPServerClient, MCPToolAdapter
from tools import ToolRegistry


def test_policy_engine_violation():
    engine = PolicyEngine([PolicyRule(name="has_user_stories", check=lambda p: bool(p.get("user_stories")), error="missing stories")])
    result = engine.evaluate({})
    assert result["passed"] is False
    assert "missing stories" in result["violations"]


def test_policy_pack_builds_role_rules():
    engine = PolicyEngine(build_policy_rules(["business_examples_required"]))
    result = engine.evaluate({"business_io_examples": []})
    assert result["passed"] is False


def test_scorecard_and_release_gates():
    scorecard = build_scorecard([{"type": "llm_call_completed"}, {"type": "agent_failed"}])
    gate = evaluate_release_gates(tests_passed=True, policy_passed=True, min_success_rate=0.4, scorecard=scorecard)
    assert scorecard["llm_calls"] == 1
    assert gate["passed"] is True


def test_planning_and_replay_helpers():
    ranked = rank_plan_steps([
        {"id": "a", "impact": 5, "effort": 2},
        {"id": "b", "impact": 2, "effort": 3},
    ])
    assert ranked[0]["id"] == "a"
    assert compare_traces([{"a": 1}], [{"a": 1}])["equal"] is True


def test_replay_save_and_summary(tmp_path):
    events = [{"type": "a"}, {"type": "a"}, {"type": "b"}]
    path = save_trace(tmp_path / "trace.jsonl", events)
    assert path.exists()
    assert replay_events(events) == {"a": 2, "b": 1}


def test_workspace_manager_and_tools(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.write_text("agent", "42", "notes/a.txt", "hello")
    assert manager.read_text("agent", "42", "notes/a.txt") == "hello"
    assert manager.list_files("agent", "42") == ["notes/a.txt"]
    try:
        manager.write_text("agent", "42", "../escape.txt", "bad")
    except ValueError as exc:
        assert "escapes workspace" in str(exc)
    else:
        raise AssertionError("workspace escape was not blocked")


def test_code_executor_and_tool_stay_inside_sandbox(tmp_path):
    executor = CodeExecutor(tmp_path)
    result = executor.run_python("print('ok')")
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "ok"
    tool = make_execute_python_tool(executor)
    assert "ok" in tool.execute({"code": "print('ok')"})
    try:
        executor.run_python("print('bad')", cwd="../outside")
    except ValueError as exc:
        assert "escapes executor sandbox" in str(exc)
    else:
        raise AssertionError("executor escape was not blocked")
    try:
        executor.run_shell("cat ../../etc/passwd")
    except ValueError as exc:
        assert "path traversal" in str(exc)
    else:
        raise AssertionError("command traversal was not blocked")


def test_todo_tracker_tools_emit_events():
    events = EventRecorder()
    tracker = AgentTodoTracker(events=events, agent="agent", work_item_id="1")
    registry = ToolRegistry()
    registry.register(make_write_todos_tool(tracker))
    registry.register(make_complete_todo_tool(tracker))
    registry.register(make_list_todos_tool(tracker))
    registry.register(make_rank_plan_steps_tool())

    registry.dispatch("write_todos", {"items": ["draft", "review"]})
    registry.dispatch("complete_todo", {"id": "todo-1", "notes": "done"})

    assert "todo-2" in registry.dispatch("list_todos", {})
    assert [event["type"] for event in events.events] == [
        AGENT_TODO_STARTED,
        AGENT_TODO_STARTED,
        AGENT_TODO_COMPLETED,
    ]
    assert '"id": "a"' in registry.dispatch(
        "rank_plan_steps",
        {"steps": [{"id": "a", "impact": 2, "effort": 1}]},
    )


def test_delegation_dispatcher_and_tool_emit_child_artifact_event():
    events = EventRecorder()

    class ChildAgent:
        artifact_type = "child"
        work_item_id = None

        def execute_stage(self, payload):
            return {"echo": payload["value"]}

        def validate_artifact(self, artifact):
            return artifact

    dispatcher = AgentTaskDispatcher(lambda key: ChildAgent(), events=events, parent_agent="parent")
    artifact = dispatcher.dispatch("child_agent", {"value": 3}, work_item_id="wi")
    assert artifact == {"echo": 3}
    assert [event["type"] for event in events.events] == [
        AGENT_DELEGATION_STARTED,
        ARTIFACT_CREATED,
        AGENT_DELEGATION_COMPLETED,
    ]
    assert events.events[-1]["payload"]["depth"] == 1

    tool = make_delegate_task_tool(dispatcher)
    assert '"echo": 4' in tool.execute(
        {"agent": "child_agent", "payload": {"value": 4}, "work_item_id": "wi"}
    )


def test_mcp_adapter_registers_tools_and_emits_events():
    events = EventRecorder()
    client = MCPServerClient(
        name="local",
        tools=[
            {
                "name": "echo",
                "description": "echo input",
                "handler": lambda args: args["text"],
                "parameters": {"type": "object"},
            }
        ],
    )
    registry = ToolRegistry()
    MCPToolAdapter(client, events=events, agent="agent", work_item_id="wi").register_tools(registry)

    assert registry.dispatch("mcp_local_echo", {"text": "hello"}) == "hello"
    assert [event["type"] for event in events.events] == [
        MCP_TOOL_INVOKED,
        MCP_TOOL_COMPLETED,
    ]
    assert "latency_ms" in events.events[-1]["payload"]


def test_provider_registry_orders_configured_providers():
    class Provider:
        def __init__(self, name):
            self.name = name

    registry = ProviderRegistry([Provider("a"), Provider("b"), Provider("a")])
    assert [provider.name for provider in registry.ordered(["b", "a"])] == ["b", "a", "a"]
    assert registry.ordered([]) == []


def test_feedback_record_written(tmp_path):
    record = append_feedback(
        tmp_path / "feedback.jsonl",
        "wi",
        "approved",
        decided_by="reviewer",
        comments="ok",
    )
    assert record["status"] == "approved"
    assert "approved" in (tmp_path / "feedback.jsonl").read_text(encoding="utf-8")


def test_release_gate_event_shape():
    events = EventRecorder()
    result = evaluate_release_gates(
        tests_passed=True,
        policy_passed=True,
        min_success_rate=0.5,
        scorecard={"success_rate": 1.0},
    )
    events.emit(RELEASE_GATE_EVALUATED, "agent", "wi", **result)
    assert events.events[-1]["payload"]["passed"] is True
