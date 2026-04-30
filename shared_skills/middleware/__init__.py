from typing import Any, Dict, Optional, Protocol, runtime_checkable

@runtime_checkable
class Middleware(Protocol):
    def before_agent(self, context: Dict[str, Any]) -> Dict[str, Any]: ...
    def before_model(self, prompt: str, context: Dict[str, Any]) -> str: ...
    def after_model(self, response: Optional[str], context: Dict[str, Any]) -> Optional[str]: ...
    def after_agent(self, result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]: ...

class BaseMiddleware:
    def before_agent(self, context): return context
    def before_model(self, prompt, context): return prompt
    def after_model(self, response, context): return response
    def after_agent(self, result, context): return result
