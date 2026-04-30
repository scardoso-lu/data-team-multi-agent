from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def complete(self, prompt: str, timeout_seconds: int) -> str | None:
        ...
