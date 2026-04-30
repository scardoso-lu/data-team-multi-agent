import json

from tools import Tool


def make_execute_python_tool(executor):
    return Tool(
        name="execute_python",
        description="Run Python code inside the configured sandbox.",
        parameters={"type": "object", "properties": {"code": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["code"]},
        execute=lambda args: json.dumps(executor.run_python(args["code"], cwd=args.get("cwd"))),
    )


def make_execute_shell_tool(executor):
    return Tool(
        name="execute_shell",
        description="Run a shell command inside the configured sandbox.",
        parameters={"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["command"]},
        execute=lambda args: json.dumps(executor.run_shell(args["command"], cwd=args.get("cwd"))),
    )
