from dataclasses import dataclass, field
import time

from events import AGENT_TODO_COMPLETED, AGENT_TODO_SKIPPED, AGENT_TODO_STARTED


@dataclass
class TodoItem:
    id: str
    text: str
    status: str = "pending"
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class AgentTodoTracker:
    def __init__(self, events=None, agent="unknown", work_item_id=None):
        self.events = events
        self.agent = agent
        self.work_item_id = work_item_id
        self._items = []

    def add_todo(self, text, item_id=None):
        item = TodoItem(id=item_id or f"todo-{len(self._items) + 1}", text=text)
        self._items.append(item)
        if self.events:
            self.events.emit(
                AGENT_TODO_STARTED,
                self.agent,
                self.work_item_id,
                id=item.id,
                text=item.text,
            )
        return item

    def write_todos(self, items):
        self._items = []
        for index, text in enumerate(items, start=1):
            self.add_todo(str(text), item_id=f"todo-{index}")
        return list(self._items)

    def get(self, item_id):
        for item in self._items:
            if item.id == item_id:
                return item
        raise KeyError(f"Unknown todo item: {item_id}")

    def complete_todo(self, item_id, notes=""):
        item = self.get(item_id)
        item.status = "done"
        item.notes = notes
        item.completed_at = time.time()
        if self.events:
            self.events.emit(
                AGENT_TODO_COMPLETED,
                self.agent,
                self.work_item_id,
                id=item.id,
                notes=notes,
            )
        return item

    def skip_todo(self, item_id, notes=""):
        item = self.get(item_id)
        item.status = "skipped"
        item.notes = notes
        item.completed_at = time.time()
        if self.events:
            self.events.emit(
                AGENT_TODO_SKIPPED,
                self.agent,
                self.work_item_id,
                id=item.id,
                notes=notes,
            )
        return item

    def list_todos(self):
        return list(self._items)

    def all_done(self):
        return bool(self._items) and all(item.status in ("done", "skipped") for item in self._items)

    def summary(self):
        marker = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "skipped": "[-]"}
        return "\n".join(
            f"{marker.get(item.status, '[ ]')} {item.id}: {item.text}"
            for item in self._items
        )


def rank_plan_steps(steps):
    scored = []
    for step in steps:
        score = (2 if step.get("blocked") else 0) + int(step.get("impact", 0)) - int(step.get("effort", 0))
        scored.append({**step, "score": score})
    return sorted(scored, key=lambda s: s["score"], reverse=True)
