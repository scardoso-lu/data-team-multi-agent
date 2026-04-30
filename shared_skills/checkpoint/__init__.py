import json, os
from pathlib import Path
from time import time

def checkpoint_path(base_dir, agent_key, work_item_id):
    return Path(base_dir) / agent_key / f"{work_item_id}.json"

def write_checkpoint(base_dir, agent_key, work_item_id, stage="claimed"):
    path = checkpoint_path(base_dir, agent_key, work_item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({"agent_key":agent_key,"work_item_id":work_item_id,"stage":stage,"claimed_at":time()}, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def clear_checkpoint(base_dir, agent_key, work_item_id):
    checkpoint_path(base_dir, agent_key, work_item_id).unlink(missing_ok=True)

def list_stale_checkpoints(base_dir, agent_key, timeout_seconds):
    directory = Path(base_dir) / agent_key
    if not directory.exists(): return []
    stale=[]; now=time()
    for path in directory.glob('*.json'):
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if now - record.get('claimed_at', now) > timeout_seconds: stale.append(record)
        except Exception:
            continue
    return stale
