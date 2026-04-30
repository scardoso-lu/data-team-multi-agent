import json
from pathlib import Path

def load_trace(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def compare_traces(left, right):
    return {"equal": left == right, "left_count": len(left), "right_count": len(right)}
