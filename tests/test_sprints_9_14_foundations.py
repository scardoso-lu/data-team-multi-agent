from evaluation import build_scorecard
from planning import rank_plan_steps
from policy import PolicyEngine, PolicyRule
from release_gates import evaluate_release_gates
from replay import compare_traces


def test_policy_engine_violation():
    engine = PolicyEngine([PolicyRule(name="has_user_stories", check=lambda p: bool(p.get("user_stories")), error="missing stories")])
    result = engine.evaluate({})
    assert result["passed"] is False
    assert "missing stories" in result["violations"]


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
