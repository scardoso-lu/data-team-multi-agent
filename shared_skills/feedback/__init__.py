import json
from pathlib import Path
from time import time

def append_feedback(path, work_item_id, status, decided_by=None, comments=None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time(),
        "work_item_id": work_item_id,
        "status": status,
        "decided_by": decided_by,
        "comments": comments,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return record
