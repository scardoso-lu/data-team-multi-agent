def _require_mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_key(mapping, key, name):
    if key not in mapping:
        raise ValueError(f"{name} missing required key: {key}")
    return mapping[key]


def validate_architecture_artifact(artifact):
    artifact = _require_mapping(artifact, "architecture artifact")
    tables = _require_key(artifact, "tables", "architecture artifact")
    relationships = _require_key(artifact, "relationships", "architecture artifact")
    if not isinstance(tables, list) or not tables:
        raise ValueError("architecture artifact tables must be a non-empty list")
    if not isinstance(relationships, dict):
        raise ValueError("architecture artifact relationships must be a mapping")
    return artifact


def validate_fabric_artifact(artifact):
    artifact = _require_mapping(artifact, "fabric artifact")
    workspace = _require_key(artifact, "workspace", "fabric artifact")
    pipelines = _require_key(artifact, "pipelines", "fabric artifact")
    if not isinstance(workspace, str) or not workspace:
        raise ValueError("fabric artifact workspace must be a non-empty string")
    if not isinstance(pipelines, list) or not pipelines:
        raise ValueError("fabric artifact pipelines must be a non-empty list")
    return artifact


def validate_quality_artifact(artifact):
    artifact = _require_mapping(artifact, "quality artifact")
    if not artifact:
        raise ValueError("quality artifact must not be empty")
    for pipeline_name, result in artifact.items():
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
    if not isinstance(tables, list) or not tables:
        raise ValueError("semantic model artifact tables must be a non-empty list")
    if not isinstance(relationships, list):
        raise ValueError("semantic model artifact relationships must be a list")
    return artifact


def validate_governance_artifact(artifact):
    artifact = _require_mapping(artifact, "governance artifact")
    required_sections = ["architecture", "engineering", "qa", "analytics", "governance"]
    for section in required_sections:
        _require_key(artifact, section, "governance artifact")
    return artifact
