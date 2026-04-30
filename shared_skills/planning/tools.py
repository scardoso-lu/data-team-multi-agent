import json

from planning import rank_plan_steps
from tools import Tool


def make_write_todos_tool(tracker):
    return Tool(
        name="write_todos",
        description="Replace the current todo list. Pass {'items': ['step 1', ...]}.",
        parameters={
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "required": ["items"],
        },
        execute=lambda args: _write_todos(tracker, args),
    )


def make_complete_todo_tool(tracker):
    return Tool(
        name="complete_todo",
        description="Mark one todo item as done. Pass {'id': 'todo-1', 'notes': '...'}",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}, "notes": {"type": "string"}},
            "required": ["id"],
        },
        execute=lambda args: _complete_todo(tracker, args),
    )


def make_list_todos_tool(tracker):
    return Tool(
        name="list_todos",
        description="List the current todo items.",
        parameters={"type": "object", "properties": {}},
        execute=lambda args: tracker.summary(),
    )


def make_rank_plan_steps_tool():
    return Tool(
        name="rank_plan_steps",
        description="Rank candidate plan steps by impact, effort, and blocked status.",
        parameters={
            "type": "object",
            "properties": {"steps": {"type": "array", "items": {"type": "object"}}},
            "required": ["steps"],
        },
        execute=lambda args: json.dumps(rank_plan_steps(args.get("steps", []))),
    )


def _write_todos(tracker, args):
    items = args.get("items", [])
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    tracker.write_todos(items)
    return tracker.summary()


def _complete_todo(tracker, args):
    item = tracker.complete_todo(args["id"], notes=args.get("notes", ""))
    return f"Marked {item.id} done.\n{tracker.summary()}"
