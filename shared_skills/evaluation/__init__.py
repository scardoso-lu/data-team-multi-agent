import json
from pathlib import Path


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


def save_scorecard(path, scorecard):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    return p
