import json, os
from pathlib import Path
from threading import Lock
from time import time

class AgentMemoryStore:
    def __init__(self, path):
        self.path = Path(path); self._lock = Lock(); self._data = self._load()
    def _load(self):
        if not self.path.exists(): return {}
        try: return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception: return {}
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding='utf-8')
        os.replace(tmp, self.path)
    def read(self):
        with self._lock: return dict(self._data)
    def update(self, key, value):
        with self._lock:
            self._data[key] = {"value": value, "updated_at": time()}; self._save()
    def forget(self, key):
        with self._lock: self._data.pop(key, None); self._save()
    def summary(self, max_entries=10):
        with self._lock:
            if not self._data: return ""
            entries = sorted(self._data.items(), key=lambda kv: kv[1].get('updated_at',0), reverse=True)[:max_entries]
        return "\n".join(["Agent memory (most recent):"] + [f"  - {k}: {v['value']}" for k,v in entries])
