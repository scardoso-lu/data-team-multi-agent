from typing import Any, Dict, List, Literal, TypedDict


class AcceptanceCriterion(TypedDict):
    done: Literal["", "X"]
    item: str


class BusinessIOExample(TypedDict):
    input: Dict[str, Any]
    expected_output: Dict[str, Any]


class UserStory(TypedDict):
    title: str
    user_story: str
    specification: str
    acceptance_criteria: List[AcceptanceCriterion]
    business_io_examples: List[BusinessIOExample]


class ArchitectureArtifact(TypedDict, total=False):
    tables: List[str]
    relationships: Dict[str, Any]
    business_io_examples: List[BusinessIOExample]
    user_stories: List[UserStory]


class FabricArtifact(TypedDict, total=False):
    execution_mode: Literal["human_required"]
    proposed_workspace: str
    pipelines: List[str]
    business_io_examples: List[BusinessIOExample]
    user_stories: List[UserStory]


class PipelineQualityResult(TypedDict, total=False):
    status: str
    issues: List[Any]


class QualityArtifact(TypedDict, total=False):
    checks: Dict[str, PipelineQualityResult]
    acceptance_tests: Dict[str, Any]
    business_io_examples: List[BusinessIOExample]


class SemanticModelArtifact(TypedDict, total=False):
    tables: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    business_io_examples: List[BusinessIOExample]


class GovernanceArtifact(TypedDict, total=False):
    architecture: str
    engineering: str
    qa: str
    analytics: str
    governance: str
