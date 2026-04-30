import json
from tools import Tool


def make_get_work_item_details_tool(ado):
    def execute(args):
        return json.dumps(ado.get_work_item_details(args.get("work_item_id")), default=str)
    return Tool("get_work_item_details", "Fetch full details of an ADO work item by ID.", {"type":"object","properties":{"work_item_id":{"type":"string"}},"required":["work_item_id"]}, execute)


def make_post_comment_tool(teams):
    def execute(args):
        teams.send_notification(
            title=args.get("title", "Tool comment"),
            message=args.get("message", ""),
            work_item_id=args.get("work_item_id"),
        )
        return "comment_posted"

    return Tool(
        "post_comment",
        "Post a comment/notification to a work item thread.",
        {
            "type": "object",
            "properties": {
                "work_item_id": {"type": "string"},
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["work_item_id", "message"],
        },
        execute,
    )


def make_read_artifact_tool(ado):
    def execute(args):
        return json.dumps(ado.get_work_item_details(args.get("work_item_id")), default=str)

    return Tool(
        "read_artifact",
        "Read stored work item artifact payload.",
        {"type": "object", "properties": {"work_item_id": {"type": "string"}}, "required": ["work_item_id"]},
        execute,
    )
