MIN_BUSINESS_IO_EXAMPLES = 3
EXPLORATION_CONFIRMATION_KEYS = (
    "human_confirmed_exploration",
    "exploration_confirmed",
    "Custom.HumanConfirmedExploration",
    "Custom.ExplorationConfirmed",
    "Custom.IsExplorationTopic",
)

EXPLORATION_CONFIRMATION_TAGS = {
    "exploration",
    "explorationconfirmed",
    "exploration-confirmed",
    "is_exploration_topic",
}


def _require_mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_key(mapping, key, name):
    if key not in mapping:
        raise ValueError(f"{name} missing required key: {key}")
    return mapping[key]


def validate_business_io_examples(examples, name="business input/output examples"):
    if not isinstance(examples, list):
        raise ValueError(f"{name} must be a list")
    if len(examples) < MIN_BUSINESS_IO_EXAMPLES:
        raise ValueError(
            f"{name} must include at least {MIN_BUSINESS_IO_EXAMPLES} examples"
        )
    for index, example in enumerate(examples, start=1):
        example = _require_mapping(example, f"{name} item {index}")
        _require_key(example, "input", f"{name} item {index}")
        _require_key(example, "expected_output", f"{name} item {index}")
    return examples


def extract_business_io_examples(value):
    value = _require_mapping(value, "business requirements")
    for key in ("business_io_examples", "input_output_examples", "examples"):
        if key in value:
            return validate_business_io_examples(value[key])
    raise ValueError(
        "business requirements missing required key: business_io_examples"
    )


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "confirmed", "approved"}
    return False


def is_human_confirmed_exploration(value):
    value = _require_mapping(value, "business requirements")
    fields = value.get("fields", {})
    for key in EXPLORATION_CONFIRMATION_KEYS:
        if _truthy(value.get(key)):
            return True
        if isinstance(fields, dict) and _truthy(fields.get(key)):
            return True

    tags = value.get("System.Tags") or value.get("tags")
    if isinstance(fields, dict):
        tags = tags or fields.get("System.Tags")
    if isinstance(tags, str):
        normalized_tags = {tag.strip().lower() for tag in tags.split(";")}
        return bool(EXPLORATION_CONFIRMATION_TAGS & normalized_tags)
    if isinstance(tags, list):
        normalized_tags = {
            tag.strip().lower()
            for tag in tags
            if isinstance(tag, str) and tag.strip()
        }
        return bool(EXPLORATION_CONFIRMATION_TAGS & normalized_tags)
    return False


def build_exploration_business_io_examples(requirements):
    requirements = _require_mapping(requirements, "business requirements")
    title = _work_item_title(requirements)
    description = _work_item_description(requirements, title)
    return [
        {
            "input": {
                "exploration_topic": title,
                "business_context": description,
                "question": "What data sources, entities, and stakeholders define the topic?",
            },
            "expected_output": {
                "validated_specification_section": "Scope, candidate sources, core entities, and owners are identified for human review.",
            },
            "generated_by_agent": True,
            "requires_human_validation": True,
        },
        {
            "input": {
                "exploration_topic": title,
                "business_context": description,
                "question": "What measurable outputs or decisions should this exploration support?",
            },
            "expected_output": {
                "validated_specification_section": "Candidate outputs, success signals, and unresolved assumptions are listed for human validation.",
            },
            "generated_by_agent": True,
            "requires_human_validation": True,
        },
        {
            "input": {
                "exploration_topic": title,
                "business_context": description,
                "question": "What implementation plan can safely test the exploration assumptions?",
            },
            "expected_output": {
                "validated_specification_section": "A reviewable Bronze/Silver/Gold exploration plan is drafted with explicit assumptions and validation tasks.",
            },
            "generated_by_agent": True,
            "requires_human_validation": True,
        },
    ]


def _value_text(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("title", "summary", "description", "requirements", "details"):
            text = _value_text(value.get(key), "")
            if text:
                return text
    return fallback


def _field_text(mapping, *keys):
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _work_item_title(requirements):
    fields = requirements.get("fields", {})
    return _value_text(
        requirements.get("title")
        or requirements.get("System.Title")
        or _field_text(fields, "System.Title", "Title")
        or _field_text(requirements, "Title"),
        "Implement the requested data capability",
    )


def _work_item_description(requirements, fallback):
    fields = requirements.get("fields", {})
    return _value_text(
        requirements.get("description")
        or requirements.get("System.Description")
        or _field_text(fields, "System.Description", "Description")
        or _field_text(requirements, "Description")
        or requirements.get("requirements")
        or requirements.get("System.AcceptanceCriteria")
        or _field_text(fields, "Microsoft.VSTS.Common.AcceptanceCriteria", "System.AcceptanceCriteria")
        or _field_text(requirements, "Microsoft.VSTS.Common.AcceptanceCriteria"),
        fallback,
    )


def _humanize_identifier(value, fallback):
    if not isinstance(value, str) or not value.strip():
        return fallback
    text = value.strip().replace("_", " ").replace("-", " ")
    return " ".join(part for part in text.split() if part)


def _example_mapping_values(business_io_examples, section):
    values = []
    for example in business_io_examples:
        if not isinstance(example, dict):
            continue
        mapping = example.get(section)
        if isinstance(mapping, dict):
            values.extend(mapping.keys())
    return values


def _infer_source_label(business_io_examples):
    input_keys = _example_mapping_values(business_io_examples, "input")
    for key in input_keys:
        key_text = str(key).lower()
        if any(part in key_text for part in ("source", "file", "url", "portal", "input")):
            return _humanize_identifier(str(key), "Source data")
    if input_keys:
        return _humanize_identifier(str(input_keys[0]), "Source data")
    return "Source data"


def _infer_target_label(business_io_examples):
    output_keys = _example_mapping_values(business_io_examples, "expected_output")
    for key in output_keys:
        key_text = str(key).lower()
        if any(part in key_text for part in ("target", "table", "output", "dataset")):
            return _humanize_identifier(str(key), "Target output")
    if output_keys:
        return _humanize_identifier(str(output_keys[0]), "Target output")
    return "Target output"


def _mermaid_node_id(label):
    words = "".join(char if char.isalnum() else " " for char in label).title().split()
    node_id = "".join(words)
    return node_id or "Step"


def build_flow_specification(title, description, business_io_examples):
    """Build a deterministic flow-style implementation specification."""
    source_label = _infer_source_label(business_io_examples)
    target_label = _infer_target_label(business_io_examples)
    title_label = _humanize_identifier(title, "Requested data capability")
    target_node = _mermaid_node_id(target_label)
    source_node = _mermaid_node_id(source_label)
    transform_label = f"Transform and Load {title_label}"
    transform_node = _mermaid_node_id(transform_label)
    context = description if description and description != title else "Insufficient information available."
    data_context = (
        "Business input/output examples define the accepted inputs and expected outputs."
        if business_io_examples
        else "Insufficient information available."
    )
    return "\n".join(
        [
            "## Flow",
            context,
            "",
            data_context,
            "",
            "```mermaid",
            "flowchart LR",
            f"    {source_node}[{source_label}] --> IngestSourceData[Ingest Source Data];",
            "    IngestSourceData --> ValidateInputData[Validate Input Data];",
            "    ValidateInputData --> CheckInputUsable{Check Input Usable};",
            f"    CheckInputUsable -- Yes --> {transform_node}[{transform_label}];",
            "    CheckInputUsable -- No --> StopPipeline[Stop Pipeline];",
            f"    {transform_node} --> VerifyExpectedOutput[Verify Expected Output];",
            f"    VerifyExpectedOutput --> {target_node}[{target_label}];",
            "",
            "```",
            "",
            "## Steps",
            (
                f"1. **Ingest Source Data**: Reads the required source data for {title_label}. "
                "Only proceed when the source can be retrieved."
            ),
            (
                "2. **Validate Input Data**: Checks that the retrieved data is present, readable, "
                "and contains the fields needed by the accepted examples. Only if step 1 succeeded:"
            ),
            "   - If the input is missing, unreadable, or empty: Stops the pipeline immediately.",
            "   - Otherwise: Passes the input data to the transformation process.",
            (
                f"3. **Check Input Usable**: Determines if validation passed. Only if step 2 succeeded:"
            ),
            "   - If validation failed: Stops the pipeline.",
            "   - Otherwise: Passes the data to the transformation and load stage.",
            (
                f"4. **{transform_label}**: Applies the business rules from the work item and "
                "uses the provided input/output examples as transformation targets."
            ),
            (
                "5. **Verify Expected Output**: Compares produced records to every expected_output "
                "example and records any mismatch for review."
            ),
            (
                f"6. **{target_label}**: Stores or exposes the validated output required by the "
                "work item."
            ),
        ]
    )


def build_default_user_stories(requirements, business_io_examples):
    """Build engineer-ready user stories when the LLM does not provide them."""
    requirements = _require_mapping(requirements, "business requirements")
    title = _work_item_title(requirements)
    description = _work_item_description(requirements, title)
    return [
        {
            "title": title,
            "user_story": (
                f"As a data engineer, I want to implement {title} so that the "
                "approved business outcome is available in the data platform."
            ),
            "specification": build_flow_specification(
                title,
                description,
                business_io_examples,
            ),
            "acceptance_criteria": [
                {
                    "done": "",
                    "item": "The implementation follows the documented flowchart and steps.",
                },
                {
                    "done": "",
                    "item": "Each business input/output example is used as an acceptance target.",
                },
                {
                    "done": "",
                    "item": "Privileged Fabric deployment and permission changes remain human-executed.",
                },
            ],
            "business_io_examples": business_io_examples,
        }
    ]


def normalize_acceptance_criteria(criteria):
    normalized = []
    for criterion in criteria:
        if isinstance(criterion, str):
            normalized.append({"done": "", "item": criterion})
            continue
        criterion = _require_mapping(criterion, "acceptance criterion")
        normalized.append(
            {
                "done": criterion.get("done", ""),
                "item": _require_key(criterion, "item", "acceptance criterion"),
            }
        )
    return normalized


def normalize_user_stories(user_stories):
    """Convert older story drafts into the current engineer-checklist contract."""
    if not isinstance(user_stories, list):
        return user_stories
    normalized = []
    for story in user_stories:
        if not isinstance(story, dict):
            normalized.append(story)
            continue
        story = dict(story)
        if "acceptance_criteria" in story:
            story["acceptance_criteria"] = normalize_acceptance_criteria(
                story["acceptance_criteria"]
            )
        normalized.append(story)
    return normalized


def work_item_type_from_details(details):
    details = _require_mapping(details, "work item details")
    fields = details.get("fields", {})
    if isinstance(fields, dict):
        for key in ("System.WorkItemType", "WorkItemType"):
            value = fields.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("System.WorkItemType", "work_item_type", "workItemType", "type"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def is_parent_work_item_type(work_item_type):
    return str(work_item_type).strip().lower() in {"epic", "feature"}


def validate_user_stories(user_stories, name="user stories"):
    if not isinstance(user_stories, list) or not user_stories:
        raise ValueError(f"{name} must be a non-empty list")
    for index, story in enumerate(user_stories, start=1):
        story = _require_mapping(story, f"{name} item {index}")
        _require_key(story, "title", f"{name} item {index}")
        _require_key(story, "user_story", f"{name} item {index}")
        _require_key(story, "specification", f"{name} item {index}")
        criteria = _require_key(story, "acceptance_criteria", f"{name} item {index}")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"{name} item {index} acceptance_criteria must be a non-empty list")
        for criterion_index, criterion in enumerate(criteria, start=1):
            criterion = _require_mapping(
                criterion,
                f"{name} item {index} acceptance_criteria item {criterion_index}",
            )
            done = _require_key(
                criterion,
                "done",
                f"{name} item {index} acceptance_criteria item {criterion_index}",
            )
            if done not in ("", "X"):
                raise ValueError(
                    f"{name} item {index} acceptance_criteria item {criterion_index} "
                    "done must be empty or X"
                )
            item = _require_key(
                criterion,
                "item",
                f"{name} item {index} acceptance_criteria item {criterion_index}",
            )
            if not isinstance(item, str) or not item:
                raise ValueError(
                    f"{name} item {index} acceptance_criteria item {criterion_index} "
                    "item must be a non-empty string"
                )
        if "business_io_examples" in story:
            validate_business_io_examples(
                story["business_io_examples"],
                f"{name} item {index} business_io_examples",
            )
    return user_stories


def validate_architecture_artifact(artifact):
    artifact = _require_mapping(artifact, "architecture artifact")
    tables = _require_key(artifact, "tables", "architecture artifact")
    relationships = _require_key(artifact, "relationships", "architecture artifact")
    examples = _require_key(artifact, "business_io_examples", "architecture artifact")
    user_stories = _require_key(artifact, "user_stories", "architecture artifact")
    if not isinstance(tables, list) or not tables:
        raise ValueError("architecture artifact tables must be a non-empty list")
    if not isinstance(relationships, dict):
        raise ValueError("architecture artifact relationships must be a mapping")
    validate_business_io_examples(examples, "architecture artifact business_io_examples")
    validate_user_stories(user_stories, "architecture artifact user_stories")
    return artifact


def validate_fabric_artifact(artifact):
    artifact = _require_mapping(artifact, "fabric artifact")
    execution_mode = _require_key(artifact, "execution_mode", "fabric artifact")
    proposed_workspace = _require_key(artifact, "proposed_workspace", "fabric artifact")
    pipelines = _require_key(artifact, "pipelines", "fabric artifact")
    examples = _require_key(artifact, "business_io_examples", "fabric artifact")
    user_stories = _require_key(artifact, "user_stories", "fabric artifact")
    if execution_mode != "human_required":
        raise ValueError("fabric artifact execution_mode must be human_required")
    if not isinstance(proposed_workspace, str) or not proposed_workspace:
        raise ValueError("fabric artifact proposed_workspace must be a non-empty string")
    if not isinstance(pipelines, list) or not pipelines:
        raise ValueError("fabric artifact pipelines must be a non-empty list")
    validate_business_io_examples(examples, "fabric artifact business_io_examples")
    validate_user_stories(user_stories, "fabric artifact user_stories")
    return artifact


def validate_quality_artifact(artifact):
    artifact = _require_mapping(artifact, "quality artifact")
    if not artifact:
        raise ValueError("quality artifact must not be empty")
    if "business_io_examples" in artifact:
        validate_business_io_examples(
            artifact["business_io_examples"],
            "quality artifact business_io_examples",
        )
        checks = _require_key(artifact, "checks", "quality artifact")
    else:
        checks = artifact
    checks = _require_mapping(checks, "quality artifact checks")
    for pipeline_name, result in checks.items():
        if not isinstance(pipeline_name, str) or not pipeline_name:
            raise ValueError("quality artifact pipeline names must be non-empty strings")
        result = _require_mapping(result, "quality result")
        _require_key(result, "status", "quality result")
        _require_key(result, "issues", "quality result")
    return artifact


def validate_semantic_model_artifact(artifact):
    artifact = _require_mapping(artifact, "semantic model artifact")
    tables = _require_key(artifact, "tables", "semantic model artifact")
    relationships = _require_key(artifact, "relationships", "semantic model artifact")
    examples = _require_key(artifact, "business_io_examples", "semantic model artifact")
    if not isinstance(tables, list) or not tables:
        raise ValueError("semantic model artifact tables must be a non-empty list")
    if not isinstance(relationships, list):
        raise ValueError("semantic model artifact relationships must be a list")
    validate_business_io_examples(examples, "semantic model artifact business_io_examples")
    return artifact


def validate_governance_artifact(artifact):
    artifact = _require_mapping(artifact, "governance artifact")
    required_sections = ["architecture", "engineering", "qa", "analytics", "governance"]
    for section in required_sections:
        _require_key(artifact, section, "governance artifact")
    return artifact


def validate_requirements_artifact(artifact):
    artifact = _require_mapping(artifact, "requirements artifact")
    _require_key(artifact, "work_item_type", "requirements artifact")
    _require_key(artifact, "is_parent", "requirements artifact")
    _require_key(artifact, "is_exploration", "requirements artifact")
    _require_key(artifact, "requirements_summary", "requirements artifact")
    examples = artifact.get("business_io_examples", [])
    if not artifact.get("is_exploration") and len(examples) < MIN_BUSINESS_IO_EXAMPLES:
        raise ValueError(
            "requirements artifact must include at least 3 business_io_examples "
            "for non-exploration work items"
        )
    return artifact
