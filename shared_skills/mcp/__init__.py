from dataclasses import dataclass
import time

from events import MCP_TOOL_COMPLETED, MCP_TOOL_FAILED, MCP_TOOL_INVOKED
from tools import Tool


@dataclass
class MCPServerClient:
    name: str
    tools: list

    def list_tools(self):
        return list(self.tools)

    def call_tool(self, tool_name, args):
        for tool in self.tools:
            if tool.get("name") == tool_name:
                handler = tool.get("handler")
                if callable(handler):
                    return handler(args)
                return tool.get("result", "")
        raise KeyError(f"Unknown MCP tool: {tool_name}")


class MCPToolAdapter:
    def __init__(self, client, events=None, agent="unknown", work_item_id=None):
        self.client = client
        self.events = events
        self.agent = agent
        self.work_item_id = work_item_id

    def register_tools(self, registry):
        for tool_def in self.client.list_tools():
            registry.register(self._tool(tool_def))

    def _tool(self, tool_def):
        name = tool_def["name"]

        def execute(args):
            if self.events:
                self.events.emit(
                    MCP_TOOL_INVOKED,
                    self.agent,
                    self.work_item_id,
                    server=self.client.name,
                    tool=name,
                    args=args,
                )
            start = time.monotonic()
            try:
                result = self.client.call_tool(name, args)
            except Exception as exc:
                if self.events:
                    self.events.emit(
                        MCP_TOOL_FAILED,
                        self.agent,
                        self.work_item_id,
                        server=self.client.name,
                        tool=name,
                        latency_ms=int((time.monotonic() - start) * 1000),
                        error=str(exc),
                    )
                raise
            if self.events:
                self.events.emit(
                    MCP_TOOL_COMPLETED,
                    self.agent,
                    self.work_item_id,
                    server=self.client.name,
                    tool=name,
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
            return str(result)

        return Tool(
            name=f"mcp_{self.client.name}_{name}",
            description=tool_def.get("description", f"MCP tool {name}"),
            parameters=tool_def.get("parameters", {"type": "object", "properties": {}}),
            execute=execute,
        )
