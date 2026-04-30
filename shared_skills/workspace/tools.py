from tools import Tool


def workspace_tools(manager, agent_key, get_work_item_id):
    return [
        make_write_file_tool(manager, agent_key, get_work_item_id),
        make_read_file_tool(manager, agent_key, get_work_item_id),
        make_list_files_tool(manager, agent_key, get_work_item_id),
        make_append_file_tool(manager, agent_key, get_work_item_id),
        make_delete_file_tool(manager, agent_key, get_work_item_id),
    ]


def make_write_file_tool(manager, agent_key, get_work_item_id):
    return Tool(
        name="write_workspace_file",
        description="Write a UTF-8 text file in the current work item workspace.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        execute=lambda args: str(manager.write_text(agent_key, get_work_item_id(), args["path"], args.get("content", ""))),
    )


def make_read_file_tool(manager, agent_key, get_work_item_id):
    return Tool(
        name="read_workspace_file",
        description="Read a UTF-8 text file from the current work item workspace.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        execute=lambda args: manager.read_text(agent_key, get_work_item_id(), args["path"]),
    )


def make_list_files_tool(manager, agent_key, get_work_item_id):
    return Tool(
        name="list_workspace_files",
        description="List files in the current work item workspace.",
        parameters={"type": "object", "properties": {}},
        execute=lambda args: "\n".join(manager.list_files(agent_key, get_work_item_id())),
    )


def make_append_file_tool(manager, agent_key, get_work_item_id):
    def append(args):
        current = ""
        try:
            current = manager.read_text(agent_key, get_work_item_id(), args["path"])
        except FileNotFoundError:
            pass
        return str(manager.write_text(agent_key, get_work_item_id(), args["path"], current + args.get("content", "")))

    return Tool(
        name="append_workspace_file",
        description="Append UTF-8 text to a file in the current work item workspace.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        execute=append,
    )


def make_delete_file_tool(manager, agent_key, get_work_item_id):
    def delete(args):
        target = manager.resolve(agent_key, get_work_item_id(), args["path"])
        target.unlink()
        return str(target)

    return Tool(
        name="delete_workspace_file",
        description="Delete a file in the current work item workspace.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        execute=delete,
    )
