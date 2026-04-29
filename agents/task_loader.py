import re
from pathlib import Path

_TASKS_FILE = Path(__file__).parent / "tasks.md"
_tasks = None


def _parse_tasks(text):
    sections = {}
    current_key = None
    current_lines = []
    for line in text.splitlines():
        match = re.match(r"^##\s+(\S+)", line)
        if match:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = match.group(1)
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _load_tasks():
    global _tasks
    if _tasks is None:
        _tasks = _parse_tasks(_TASKS_FILE.read_text(encoding="utf-8"))
    return _tasks


def load_task(key):
    """Return the LLM task string for the given agent key."""
    tasks = _load_tasks()
    if key not in tasks:
        raise KeyError(f"No task found for key '{key}' in {_TASKS_FILE}")
    return tasks[key]
