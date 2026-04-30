import json
from pathlib import Path

def load_trace(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def compare_traces(left, right):
    return {"equal": left == right, "left_count": len(left), "right_count": len(right)}

def save_trace(path, events):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as trace_file:
        for event in events:
            trace_file.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    return p

def replay_events(events, reducer=None):
    state = {}
    for event in events:
        if reducer is None:
            state[event.get("type", "unknown")] = state.get(event.get("type", "unknown"), 0) + 1
        else:
            state = reducer(state, event)
    return state
