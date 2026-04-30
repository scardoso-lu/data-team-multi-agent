from middleware import BaseMiddleware
class MemoryMiddleware(BaseMiddleware):
    def __init__(self, memory_store): self.store = memory_store
    def before_model(self, prompt, context):
        summary = self.store.summary()
        return f"{summary}\n\n{prompt}" if summary else prompt
