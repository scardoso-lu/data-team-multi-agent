# Agent LLM Tasks

Task prompts loaded at runtime by `agents/task_loader.py` via `load_task(key)`.
Each `##` heading is a task key that matches the agent's `agent_key`.
Edit the text under each heading to change what is sent to the LLM; keep
the heading names and file location stable so the loader can find them.

## requirements_analyst

Summarise the work item requirements in plain language for a data engineering audience.
Identify the core business objective, the key data entities involved, and any explicit
constraints or quality expectations stated in the work item.
Return: {"requirements_summary": "<2-4 sentence summary>"}
Do not invent details not present in the work item. Do not include example data values.

## data_architect

Design a data architecture contract from the validated requirements artifact.
The payload contains the requirements_summary, business_io_examples, and a
fallback_contract showing the expected output structure and format — follow it.
Return tables, relationships, user_stories, and business_io_examples.
Each user story must include title, user_story, specification, acceptance_criteria,
and business_io_examples. Do not invent source, target, rules, or ownership details
that are not present in the requirements; write 'Insufficient information available.'
for any missing section.

## data_engineer

Create a reviewable implementation package for Fabric Bronze, Silver, and Gold
pipelines. Do not create workspaces, deploy pipelines, run dataflows, or mutate
cloud resources. Use the business input/output examples as acceptance goals for
the human engineer. Implement from the engineer-ready user stories, where each
story contains its specification. Mark completed acceptance criteria by setting
done='X'. Return execution_mode, proposed_workspace, pipelines, user_stories,
and business_io_examples.

## qa_engineer

Produce a quality artifact for the Fabric implementation package.
For each pipeline in the payload (Bronze ingestion, Silver transformation,
Gold aggregation), generate a set of acceptance checks. Required check types
per pipeline:
  - schema: column names and types match the architecture contract
  - completeness: no unexpected null rates in key fields
  - uniqueness: primary key columns contain no duplicates
  - referential_integrity: foreign key values exist in the referenced table
  - business_rule: each business_io_example expected_output is reproduced by the pipeline

For each check set status to "passed", "failed", or "skipped" and list any issues found.
Classify each issue as "blocker", "warning", or "info". Every check must reference the
specific business_io_example it validates by its index.
Return: {"checks": {"<pipeline_name>": {"status": "...", "issues": [...]}},
         "business_io_examples": <list from payload>}

## data_analyst

Develop a semantic model from the Gold layer quality artifact. The model must define:
  - tables: each with name, grain (what one row represents), and column list
  - relationships: each with from_table, from_column, to_table, to_column, and
    cardinality (one_to_many or many_to_one)
  - measures: each with name, description, calculation (plain English formula),
    and the grain at which it is evaluated
  - certified_terms: business glossary mapping technical column names to
    business-friendly labels

Validate that every expected_output value in the business_io_examples can be derived
from the measures you define. If an expected_output field has no matching measure,
flag it under a "gaps" key.
Return: {"tables": [...], "relationships": [...], "measures": [...],
         "certified_terms": {...}, "gaps": [...],
         "business_io_examples": <list from payload>}

## data_steward

Audit the full data lifecycle artifact for governance and compliance readiness.
For each of the five lifecycle stages — architecture, engineering, qa, analytics,
governance — produce a section with:
  - verdict: "compliant", "non-compliant", or "needs-review"
  - findings: list of specific observations (data ownership, sensitivity labels,
    lineage completeness, retention policy, access controls, PII handling)
  - business_examples_preserved: true/false — confirms at least 3 input/output
    examples are carried through from this stage's artifact

Flag any stage as "non-compliant" if:
  - business_io_examples are absent or fewer than 3
  - execution_mode is not "human_required" in the engineering artifact
  - sensitivity labels or data ownership are undocumented

Return: {"architecture": {...}, "engineering": {...}, "qa": {...},
         "analytics": {...}, "governance": {...}}
