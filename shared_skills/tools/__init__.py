from dataclasses import dataclass
from typing import Any, Callable, Dict, List

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable[[Dict[str, Any]], str]
    def schema(self)->Dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}

class ToolRegistry:
    def __init__(self, events=None, agent="unknown", work_item_id=None):
        self._tools={}
        self.events = events
        self.agent = agent
        self.work_item_id = work_item_id
    def register(self, tool: Tool): self._tools[tool.name]=tool
    def schema_list(self)->List[Dict[str, Any]]: return [t.schema() for t in self._tools.values()]
    def dispatch(self, name: str, args: Dict[str, Any])->str:
        if name not in self._tools: return f"Error: unknown tool '{name}'"
        try:
            result = self._tools[name].execute(args)
            if self.events:
                self.events.emit(
                    "tool_invoked",
                    self.agent,
                    self.work_item_id,
                    tool=name,
                    args=args,
                    success=True,
                )
            return result
        except Exception as exc:
            if self.events:
                self.events.emit(
                    "tool_invoked",
                    self.agent,
                    self.work_item_id,
                    tool=name,
                    args=args,
                    success=False,
                    error=str(exc),
                )
            return f"Error executing tool '{name}': {exc}"
