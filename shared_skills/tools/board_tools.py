import json
from tools import Tool

def make_get_work_item_details_tool(ado):
    def execute(args):
        return json.dumps(ado.get_work_item_details(args.get("work_item_id")), default=str)
    return Tool("get_work_item_details", "Fetch full details of an ADO work item by ID.", {"type":"object","properties":{"work_item_id":{"type":"string"}},"required":["work_item_id"]}, execute)
