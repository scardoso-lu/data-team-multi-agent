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
    def __init__(self): self._tools={}
    def register(self, tool: Tool): self._tools[tool.name]=tool
    def schema_list(self)->List[Dict[str, Any]]: return [t.schema() for t in self._tools.values()]
    def dispatch(self, name: str, args: Dict[str, Any])->str:
        if name not in self._tools: return f"Error: unknown tool '{name}'"
        try: return self._tools[name].execute(args)
        except Exception as exc: return f"Error executing tool '{name}': {exc}"
