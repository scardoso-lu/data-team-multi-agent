def build_scorecard(events):
    total = len(events)
    failed = len([e for e in events if e.get("type") == "agent_failed"])
    llm_calls = len([e for e in events if e.get("type") == "llm_call_completed"])
    return {
        "total_events": total,
        "agent_failures": failed,
        "llm_calls": llm_calls,
        "success_rate": 0.0 if total == 0 else round((total - failed) / total, 4),
    }
