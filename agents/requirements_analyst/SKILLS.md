# Requirements Analyst Agent Skills

## Overview
The Requirements Analyst Agent validates and enriches work items before architecture
begins. It operates in the **Requirements** column of the ADO board and is the first
agent in the pipeline.

## Skills

### 1. Work Item Classification
- Determines whether the work item is a parent type (Epic, Feature) or a leaf type
  (User Story, Issue, Bug) using `work_item_type_from_details` and
  `is_parent_work_item_type` from `shared_skills/artifacts`.
- Sets `is_parent` in the requirements artifact so the Data Architect knows whether
  to create child work items or write specs to the existing item.

### 2. Business Examples Validation
- Calls `extract_business_io_examples` to confirm at least 3 input/output examples
  are present.
- Raises `WorkItemBlocked("missing_business_io_examples")` and notifies the team
  when examples are absent and the item is not a human-confirmed exploration topic.

### 3. Exploration Topic Detection
- Calls `is_human_confirmed_exploration` to detect the `is_exploration_topic` tag
  or equivalent custom fields.
- Allows exploration topics through with an empty `business_io_examples` list so the
  Data Architect can generate exploratory examples.

### 4. Requirements Summarisation
- Uses the LLM to produce a 2–4 sentence plain-language summary of the work item's
  business objective, key data entities, and constraints.
- Falls back to the work item title when no LLM CLI is available.

## Workflow
1. Claim work item from the **Requirements** column.
2. Classify work item type and detect exploration flag.
3. Validate business_io_examples; block if missing and not exploration.
4. Generate requirements summary via LLM.
5. Produce and validate the `RequirementsArtifact`.
6. Request human approval.
7. On approval, move work item to the **Architecture** column.

## Configuration
Column, next_column, and approval settings are loaded from `config/default.json`
under `agents.requirements_analyst`.
