import json
from context import compress_payload, payload_exceeds_budget
from middleware import BaseMiddleware

class SummarisationMiddleware(BaseMiddleware):
    def __init__(self, max_tokens=None, config=None, llm=None):
        configured = config.get("llm", "max_payload_tokens", default=None) if config else None
        self.max_tokens = max_tokens or configured or 30000
        self.llm = llm
    def before_model(self, prompt, context):
        payload = context.get("payload")
        if payload is None or not payload_exceeds_budget(payload, self.max_tokens):
            return prompt
        compressed = self._llm_summarise(payload) if self.llm is not None else compress_payload(payload)
        context["payload"] = compressed
        try:
            before, after = prompt.split("Input JSON:\n", 1)
            i = after.index("\n\nConstraints:")
            return before + "Input JSON:\n" + json.dumps(compressed, indent=2, sort_keys=True) + after[i:]
        except ValueError:
            return prompt
    def _llm_summarise(self, payload):
        summary = self.llm.complete_json(task="Summarise payload preserving structural fields", payload={"payload": payload}, fallback=compress_payload(payload))
        return summary if isinstance(summary, dict) else compress_payload(payload)
