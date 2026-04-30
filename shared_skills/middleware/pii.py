import re
from middleware import BaseMiddleware

_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<ssn>"),
    (re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\b"), "<cc>"),
    (re.compile(r"(?i)(secret|token|password|pat|key)\s*[:=]\s*\S+"), r"\1=<redacted>"),
]

class PIIScrubbingMiddleware(BaseMiddleware):
    def before_model(self, prompt, context):
        for pattern, replacement in _PATTERNS:
            prompt = pattern.sub(replacement, prompt)
        return prompt
