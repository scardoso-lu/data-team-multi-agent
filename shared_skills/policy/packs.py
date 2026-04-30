from policy import PolicyRule


def business_examples_required():
    return PolicyRule(
        name="business_examples_required",
        check=lambda payload: len(payload.get("business_io_examples", [])) >= 3,
        error="artifact must preserve at least 3 business_io_examples",
    )


def human_required_engineering():
    return PolicyRule(
        name="human_required_engineering",
        check=lambda payload: payload.get("execution_mode") in (None, "human_required"),
        error="engineering execution_mode must be human_required",
    )


POLICY_PACKS = {
    "business_examples_required": business_examples_required,
    "human_required_engineering": human_required_engineering,
}


def build_policy_rules(names):
    rules = []
    for name in names or []:
        factory = POLICY_PACKS.get(name)
        if factory is not None:
            rules.append(factory())
    return rules
