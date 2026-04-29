import pytest

from artifacts import (
    build_default_user_stories,
    build_exploration_business_io_examples,
    is_human_confirmed_exploration,
    validate_business_io_examples,
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
    validate_fabric_artifact(
        {
            "execution_mode": "human_required",
            "proposed_workspace": "workspace_1",
            "pipelines": ["bronze"],
            "user_stories": config.require("architecture", "user_stories"),
            "business_io_examples": config.require("architecture", "business_io_examples"),
        }
    )


def test_invalid_artifact_raises_clear_error():
    with pytest.raises(ValueError, match="proposed_workspace"):
        validate_fabric_artifact({"execution_mode": "human_required", "pipelines": ["bronze"]})


def test_business_io_examples_require_at_least_three_pairs():
    with pytest.raises(ValueError, match="at least 3"):
        validate_business_io_examples(
            [
                {"input": {"value": 1}, "expected_output": {"value": 2}},
                {"input": {"value": 2}, "expected_output": {"value": 4}},
            ]
        )


def test_acceptance_criteria_are_engineer_checklist_items():
    config = AppConfig()
    user_story = config.require("architecture", "user_stories")[0]

    assert user_story["acceptance_criteria"][0]["done"] == ""
    assert user_story["acceptance_criteria"][0]["item"]


def test_default_user_story_uses_ado_system_description():
    config = AppConfig()

    stories = build_default_user_stories(
        {
            "System.Title": "Revenue quality issue",
            "System.Description": "Use the revenue issue description as the algorithm input.",
            "business_io_examples": config.require("architecture", "business_io_examples"),
        },
        config.require("architecture", "business_io_examples"),
    )

    assert "Revenue quality issue" in stories[0]["title"]
    assert "Use the revenue issue description" in stories[0]["specification"]
    assert "## Flow" in stories[0]["specification"]
    assert "```mermaid" in stories[0]["specification"]
    assert "flowchart LR" in stories[0]["specification"]
    assert "## Steps" in stories[0]["specification"]


def test_human_confirmed_exploration_builds_fallback_examples():
    requirements = {
        "fields": {
            "System.Title": "Explore churn signals",
            "System.Description": "Find likely signals for churn analysis.",
            "Custom.ExplorationConfirmed": "true",
        }
    }

    examples = build_exploration_business_io_examples(requirements)

    assert is_human_confirmed_exploration(requirements) is True
    assert len(examples) == 3
    validate_business_io_examples(examples)
    assert examples[0]["requires_human_validation"] is True


def test_is_exploration_topic_is_read_from_tags():
    assert (
        is_human_confirmed_exploration(
            {"fields": {"System.Tags": "customer; is_exploration_topic; urgent"}}
        )
        is True
    )
    assert is_human_confirmed_exploration({"tags": ["is_exploration_topic"]}) is True
    assert is_human_confirmed_exploration({"is_exploration_topic": True}) is False
