import json

from tools import Tool


def make_delegate_task_tool(dispatcher):
    return Tool(
        name="delegate_task",
        description="Delegate a payload to another in-process agent.",
        parameters={
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "payload": {"type": "object"},
                "work_item_id": {"type": "string"},
            },
            "required": ["agent", "payload"],
        },
        execute=lambda args: json.dumps(
            dispatcher.dispatch(
                args["agent"],
                args.get("payload", {}),
                work_item_id=args.get("work_item_id"),
            ),
            default=str,
        ),
    )
