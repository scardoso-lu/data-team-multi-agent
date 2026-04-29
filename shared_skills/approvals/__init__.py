import json
import os
import uuid
from pathlib import Path
from threading import Lock
from time import time


PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
TIMED_OUT = "timed_out"


def new_approval_record(
    work_item_id,
    agent,
    stage,
    artifact_summary=None,
    artifact_links=None,
):
    approval_id = str(uuid.uuid4())
    return {
        "approval_id": approval_id,
        "work_item_id": work_item_id,
        "agent": agent,
        "stage": stage,
        "artifact_summary": artifact_summary or "",
        "artifact_links": artifact_links or [],
        "status": PENDING,
        "requested_at": time(),
        "decided_at": None,
        "decided_by": None,
        "comments": None,
    }


class InMemoryApprovalStore:
    def __init__(self):
        self.records = {}
        self._lock = Lock()

    def create(self, record):
        with self._lock:
            self.records[record["approval_id"]] = dict(record)
            return dict(record)

    def get(self, approval_id):
        with self._lock:
            record = self.records.get(approval_id)
            return dict(record) if record else None

    def decide(self, approval_id, status, decided_by=None, comments=None):
        with self._lock:
            if approval_id not in self.records:
                raise KeyError(f"Unknown approval_id: {approval_id}")
            self.records[approval_id].update(
                {
                    "status": status,
                    "decided_at": time(),
                    "decided_by": decided_by,
                    "comments": comments,
                }
            )
            return dict(self.records[approval_id])


class JsonFileApprovalStore(InMemoryApprovalStore):
    def __init__(self, path):
        self.path = Path(path)
        super().__init__()
        self._load()

    def create(self, record):
        self._load()
        created = super().create(record)
        self._save()
        return created

    def get(self, approval_id):
        self._load()
        return super().get(approval_id)

    def decide(self, approval_id, status, decided_by=None, comments=None):
        self._load()
        decided = super().decide(approval_id, status, decided_by, comments)
        self._save()
        return decided

    def _load(self):
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as approval_file:
            self.records = json.load(approval_file)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as approval_file:
            json.dump(self.records, approval_file, indent=2, sort_keys=True)
        os.replace(temporary_path, self.path)
