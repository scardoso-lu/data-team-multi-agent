# Sprint 8 — Agent & Task Refinement

## Problem statement

### `data_architect` — task is too large

The current prompt does three different jobs:

1. **Classification** — describes Epic/Feature vs leaf-item branching logic.  
   Already handled by `is_parent_work_item_type()` and `work_item_type_from_details()` in Python.

2. **Format rules** — Mermaid `flowchart LR`, `## Flow` / `## Steps` structure, `done=''`
   checklist format.  
   Already encoded in `build_flow_specification()` and `build_default_user_stories()` which
   are injected into the payload as `fallback_contract`.

3. **Core design intent** — what the LLM is actually being asked to produce.  
   This is the only part that belongs in the task prompt.

Keeping all three in the prompt causes the LLM to receive contradictory or redundant
instructions when the payload already contains the format rules, and makes the architect
responsible for concerns that the pipeline (Python code) already resolves deterministically.

**Fix:** Create a new `RequirementsAnalystAgent` that handles classification and
requirements validation before the architect runs. Trim the architect task to pure design
intent, trusting the payload for format guidance.

### `qa_engineer`, `data_analyst`, `data_steward` — tasks are too thin

Two-line prompts give the LLM no guidance on output shape, check types, or domain
conventions. Each agent will produce wildly inconsistent structures across runs because
there is no stated contract.

**Fix:** Expand each task with the expected output structure, domain-specific check
categories, and the role the business_io_examples play in each stage.

---

## New pipeline after this sprint

```
Requirements → Architecture → Engineering → QA → Analytics → Governance → Done
```

The `RequirementsAnalystAgent` occupies the new **Requirements** column. It validates,
classifies, and enriches work items so every downstream agent receives clean, structured
input.

---

## User Story 8.1 — New `RequirementsAnalystAgent`

**As a** data architect,
**I want** to receive a pre-validated, pre-classified work item with structured metadata,
**so that** my task prompt can focus purely on design rather than input validation and
type detection.

### What this agent does

| Responsibility | Currently owned by |
|---|---|
| Validate ≥3 business_io_examples exist | `DataArchitectAgent.design_architecture` |
| Detect human-confirmed exploration topics | `DataArchitectAgent.design_architecture` |
| Classify work item type (Epic/Feature vs leaf) | `DataArchitectAgent.design_architecture` |
| Produce a clean `requirements` artifact | nobody |

### Implementation

**New file:** `agents/requirements_analyst/app.py`

```python
from agents.skill_loader import SkillLoader
from agents.task_loader import load_task
from approval_server import ApprovalServer
from agent_base import BoardAgent, DependencyProvider, configure_agent_logger
from agent_runtime import WorkItemBlocked
from artifacts import (
    extract_business_io_examples,
    is_human_confirmed_exploration,
    is_parent_work_item_type,
    work_item_type_from_details,
    validate_requirements_artifact,   # new — see US 8.1b
)
from llm_integration import LocalLLMClient

logger = configure_agent_logger(__name__, "logs/requirements_analyst/requirements_analyst.log")


class RequirementsAnalystAgent(BoardAgent):
    agent_key = "requirements_analyst"
    dependency_names = ("ado", "teams")
    artifact_type = "requirements"

    def __init__(self, ado=None, teams=None, approvals=None, config=None, events=None, llm=None):
        provider = DependencyProvider(SkillLoader) if ado is None or teams is None else None
        super().__init__(
            ado=ado, teams=teams, approvals=approvals, config=config,
            events=events, dependency_provider=provider,
            approval_server_cls=ApprovalServer,
        )
        self.llm = llm or LocalLLMClient(config=self.config)

    def analyse_requirements(self, work_item):
        work_item_type = work_item_type_from_details(work_item)
        is_parent = is_parent_work_item_type(work_item_type)
        is_exploration = is_human_confirmed_exploration(work_item)

        try:
            examples = extract_business_io_examples(work_item)
        except ValueError as exc:
            if not is_exploration:
                self.teams.send_notification(
                    title=f"Work Item {self.work_item_id} Missing Business Examples",
                    message=str(exc),
                    work_item_id=self.work_item_id,
                )
                raise WorkItemBlocked("missing_business_io_examples", str(exc)) from exc
            examples = []   # exploration path — architect generates them

        summary = self.llm.complete_json(
            task=load_task("requirements_analyst"),
            payload={"work_item": work_item},
            fallback={"requirements_summary": str(work_item.get("title", ""))},
        )

        return {
            "work_item_type": work_item_type,
            "is_parent": is_parent,
            "is_exploration": is_exploration,
            "business_io_examples": examples,
            "requirements_summary": (summary or {}).get(
                "requirements_summary", str(work_item.get("title", ""))
            ),
            "original_work_item": work_item,
        }

    def execute_stage(self, work_item):
        return self.analyse_requirements(work_item)

    def validate_artifact(self, artifact):
        return validate_requirements_artifact(artifact)

    def run(self):
        super().run(logger)
```

**New file:** `agents/requirements_analyst/agent.md` — role constraints following the
same structure as the other agent.md files. Key constraint: never modify the work item
directly; only read and classify.

**New file:** `agents/requirements_analyst/SKILLS.md` — documents the classification
and validation skills.

### RequirementsArtifact validator

**File:** `shared_skills/artifacts/__init__.py`

Add:
```python
def validate_requirements_artifact(artifact):
    artifact = _require_mapping(artifact, "requirements artifact")
    _require_key(artifact, "work_item_type", "requirements artifact")
    _require_key(artifact, "is_parent", "requirements artifact")
    _require_key(artifact, "is_exploration", "requirements artifact")
    _require_key(artifact, "requirements_summary", "requirements artifact")
    # business_io_examples may be empty for exploration topics
    examples = artifact.get("business_io_examples", [])
    if not artifact.get("is_exploration") and len(examples) < MIN_BUSINESS_IO_EXAMPLES:
        raise ValueError(
            "requirements artifact must include at least 3 business_io_examples "
            "for non-exploration work items"
        )
    return artifact
```

### Config additions (`config/default.json`)

Under `agents`:
```json
"requirements_analyst": {
  "display_name": "Requirements Analyst",
  "service_name": "requirements_analyst",
  "port": 4999,
  "column": "Requirements",
  "next_column": "Architecture",
  "approval_message": "Requirements analysis for work item {work_item_id} is ready for review."
}
```

### Registry

**File:** `agents/registry.py` — add `RequirementsAnalystAgent` import and entry.

### DataArchitectAgent cleanup

Remove from `DataArchitectAgent.design_architecture`:
- `extract_business_io_examples` call and its `WorkItemBlocked` raise
- `is_human_confirmed_exploration` check
- `work_item_type_from_details` call
- `is_parent_work_item_type` branch

The architect now reads these from the incoming `RequirementsArtifact`:
```python
def execute_stage(self, requirements_artifact):
    # requirements_artifact is now the output of RequirementsAnalystAgent
    examples = requirements_artifact["business_io_examples"]
    is_parent = requirements_artifact["is_parent"]
    is_exploration = requirements_artifact["is_exploration"]
    work_item = requirements_artifact["original_work_item"]
    ...
```

**Acceptance criteria:**
- `RequirementsAnalystAgent.process_next_item()` returns `status="skipped"` with
  `reason="missing_business_io_examples"` for a work item without examples and no
  exploration flag.
- For an exploration-flagged item it returns `status="processed"` with
  `is_exploration=True` and an empty `business_io_examples`.
- `DataArchitectAgent` no longer imports `is_human_confirmed_exploration` or
  `work_item_type_from_details`.

**Tests:** `tests/test_requirements_analyst.py` (new file)
- Test: work item with 3 examples → `status="processed"`, `is_parent=False`.
- Test: Epic with 3 examples → `is_parent=True`.
- Test: missing examples, no exploration flag → `status="skipped"`, reason matches.
- Test: missing examples, exploration flag → `status="processed"`, `is_exploration=True`.

---

## User Story 8.2 — Trim `data_architect` task to design intent only

**As a** data architect LLM call,
**I want** a task prompt that states only what to design,
**so that** format rules (which are in the payload) are not duplicated or contradicted.

### New task text (replaces current `## data_architect` section in `agents/tasks.md`)

```
Design a data architecture contract from the validated requirements artifact.
The payload contains the requirements_summary, business_io_examples, is_parent flag,
and a fallback_contract showing the expected output structure and format — follow it.
Return tables, relationships, user_stories, and business_io_examples.
Each user story must include title, user_story, specification, acceptance_criteria,
and business_io_examples. Do not invent source, target, rules, or ownership details
that are not present in the requirements; write 'Insufficient information available.'
for any missing section.
```

The format rules for Mermaid and acceptance-criteria checklists move from the task
prompt into the `fallback_contract` payload key, where `build_flow_specification()` and
`build_default_user_stories()` already produce them.

**Acceptance criteria:**
- The `data_architect` section in `tasks.md` is ≤8 lines.
- All existing `tests/test_data_architect.py` tests pass without modification.

---

## User Story 8.3 — Expand `qa_engineer` task

**As a** QA engineer LLM call,
**I want** a task prompt that specifies what check types to produce and what the output
structure must look like,
**so that** quality artifacts are consistent across work items and useful for the
Data Analyst and Data Steward downstream.

### New task text (replaces current `## qa_engineer` section in `agents/tasks.md`)

```
Produce a quality artifact for the Fabric implementation package.
For each pipeline in the payload (Bronze ingestion, Silver transformation, Gold aggregation),
generate a set of acceptance checks. Required check types per pipeline:
  - schema: column names and types match the architecture contract
  - completeness: no unexpected null rates in key fields
  - uniqueness: primary key columns contain no duplicates
  - referential_integrity: foreign key values exist in the referenced table
  - business_rule: each business_io_example expected_output is reproduced by the pipeline

For each check set the status to "passed", "failed", or "skipped" and list any issues
found. Classify each issue as "blocker", "warning", or "info".
Every check must reference the specific business_io_example it validates by its index.
Return: {"checks": {"<pipeline_name>": {"status": "...", "issues": [...]}},
         "business_io_examples": <list from payload>}
```

---

## User Story 8.4 — Expand `data_analyst` task

**As a** data analyst LLM call,
**I want** a task prompt that specifies the semantic model components and how to validate
them against the business examples,
**so that** the semantic model artifact is complete enough for the Data Steward to audit
and for Power BI developers to implement.

### New task text (replaces current `## data_analyst` section in `agents/tasks.md`)

```
Develop a semantic model from the Gold layer quality artifact.
The model must define:
  - tables: each with name, grain (what one row represents), and column list
  - relationships: each with from_table, from_column, to_table, to_column, and cardinality
    (one_to_many or many_to_one)
  - measures: each with name, description, calculation (plain English formula), and the
    grain at which it is evaluated
  - certified_terms: business glossary entries mapping technical column names to
    business-friendly labels

Validate that every expected_output value in the business_io_examples can be derived
from the measures you define. If an expected_output field has no matching measure,
flag it under a "gaps" key.

Return: {"tables": [...], "relationships": [...], "measures": [...],
         "certified_terms": {...}, "gaps": [...],
         "business_io_examples": <list from payload>}
```

---

## User Story 8.5 — Expand `data_steward` task

**As a** data steward LLM call,
**I want** a task prompt that specifies what to audit at each lifecycle stage and what
the governance result structure must look like,
**so that** the audit is traceable, actionable, and sufficient for a compliance review.

### New task text (replaces current `## data_steward` section in `agents/tasks.md`)

```
Audit the full data lifecycle artifact for governance and compliance readiness.
For each of the five lifecycle stages — architecture, engineering, qa, analytics,
governance — produce a section with:
  - verdict: "compliant", "non-compliant", or "needs-review"
  - findings: list of specific observations (data ownership, sensitivity labels,
    lineage completeness, retention policy, access controls, PII handling)
  - business_examples_preserved: true/false — confirms at least 3 input/output
    examples are carried through from this stage's artifact

The governance stage section audits whether the other four sections are complete and
consistent, not the underlying data itself.

Flag any stage as "non-compliant" if:
  - business_io_examples are absent or fewer than 3
  - execution_mode is not "human_required" in the engineering artifact
  - sensitivity labels or data ownership are undocumented

Return: {"architecture": {...}, "engineering": {...}, "qa": {...},
         "analytics": {...}, "governance": {...}}
```

---

## User Story 8.6 — Add `requirements_analyst` task to `agents/tasks.md`

**As a** requirements analyst LLM call,
**I want** a task prompt that asks for a concise summary of the work item requirements,
**so that** downstream agents receive a human-readable summary alongside the structured
classification data that Python already extracted.

### New task text (new `## requirements_analyst` section in `agents/tasks.md`)

```
Summarise the work item requirements in plain language for a data engineering audience.
Identify the core business objective, the key data entities involved, and any explicit
constraints or quality expectations stated in the work item.
Return: {"requirements_summary": "<2-4 sentence summary>"}
Do not invent details not present in the work item. Do not include example data values.
```

---

## User Story 8.7 — Update `config/default.json` and harness for new pipeline stage

**As a** harness runner,
**I want** the local harness to include the `RequirementsAnalystAgent` as the first
stage,
**so that** end-to-end harness runs exercise the full six-stage pipeline.

### Implementation

**File:** `harness/run.py`

Add `RequirementsAnalystAgent` as the first agent in the `agents` list in
`build_harness()`. Prepopulate the `Requirements` column in `FakeBoardClient`:

```python
from agents.requirements_analyst.app import RequirementsAnalystAgent

first_column = config.agent_value("requirements_analyst", "column")
board = FakeBoardClient(
    columns={first_column: [work_item_id]},
    details={work_item_id: { ... }}   # same as before
)

agents = [
    RequirementsAnalystAgent(...),
    DataArchitectAgent(...),
    ...
]
```

**File:** `config/default.json`

Add `"Requirements"` as the first board column in the `requirements_analyst` agent
config (see US 8.1). No other column config needs to change; the architect's `column`
stays `"Architecture"`.

**Acceptance criteria:**
- `make harness` runs all six agents without error.
- The requirements artifact produced by stage 1 is stored on the fake board and
  consumed by the architect in stage 2.
- `uv run pytest tests/ -v` passes with no regressions.
