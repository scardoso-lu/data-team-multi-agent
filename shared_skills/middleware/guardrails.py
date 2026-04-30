from agent_runtime import WorkItemBlocked
from artifacts import extract_business_io_examples, is_human_confirmed_exploration
from middleware import BaseMiddleware

class BusinessExamplesGuardrailMiddleware(BaseMiddleware):
    def before_agent(self, context):
        requirements = context.get("stage_input", {})
        try:
            extract_business_io_examples(requirements)
        except ValueError as exc:
            if is_human_confirmed_exploration(requirements):
                return context
            raise WorkItemBlocked("missing_business_io_examples", str(exc)) from exc
        return context
