import os
import sys

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from artifacts import (
    validate_architecture_artifact,
    validate_fabric_artifact,
    validate_governance_artifact,
    validate_quality_artifact,
    validate_semantic_model_artifact,
)
from config import AppConfig


def test_configured_artifacts_are_valid():
    config = AppConfig()

    validate_architecture_artifact(config.require("architecture"))
    validate_quality_artifact(config.require("qa", "quality_results"))
    validate_semantic_model_artifact(config.require("semantic_model"))
    validate_governance_artifact(config.require("governance", "audit_results"))
    validate_fabric_artifact({"workspace": "workspace_1", "pipelines": ["bronze"]})


def test_invalid_artifact_raises_clear_error():
    with pytest.raises(ValueError, match="workspace"):
        validate_fabric_artifact({"pipelines": ["bronze"]})
