from middleware import BaseMiddleware
DEFAULT_MAX_CHARS = 120_000
class ContextSizeMiddleware(BaseMiddleware):
    def __init__(self, max_chars=None, config=None):
        configured = config.get("llm", "max_prompt_chars", default=None) if config else None
        self.max_chars = max_chars or configured or DEFAULT_MAX_CHARS
    def before_model(self, prompt, context):
        if len(prompt) <= self.max_chars:
            return prompt
        return prompt[: self.max_chars] + "\n\n[PROMPT TRUNCATED — payload exceeded context budget]"
