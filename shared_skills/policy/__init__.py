from dataclasses import dataclass
from typing import Any, Callable, Dict, List

@dataclass
class PolicyRule:
    name: str
    check: Callable[[Dict[str, Any]], bool]
    error: str

class PolicyEngine:
    def __init__(self, rules: List[PolicyRule] | None = None):
        self.rules = list(rules or [])
    def add_rule(self, rule: PolicyRule):
        self.rules.append(rule)
    def evaluate(self, payload: Dict[str, Any]):
        violations = [r.error for r in self.rules if not r.check(payload)]
        return {"passed": not violations, "violations": violations}
