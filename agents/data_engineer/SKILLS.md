# Data Engineer Agent Skills

## Overview
The Data Engineer Agent prepares a reviewable Medallion implementation package for Microsoft Fabric. It operates in the **Engineering** column of the Azure DevOps (ADO) Kanban board and does not create, deploy, or mutate Fabric resources.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Publish reviewable implementation artifacts for the work item.
  - Move work items to the next column (QA).

### 2. ADO Discussion Integration
- **Description**: Writes approval requests and status updates to Azure DevOps work item discussion.
- **Actions**:
  - Send approval requests for pipeline implementations.
  - Notify stakeholders of progress and approvals.

### 3. Medallion Implementation Package
- **Description**: Prepares the Bronze, Silver, and Gold implementation package for a human engineer.
- **Actions**:
  - Use Architect-provided business input/output examples as implementation acceptance targets.
  - Use Architect-provided user stories as the implementation backlog.
  - Describe proposed Bronze ingestion, Silver transformation, and Gold aggregation steps.
  - Mark Fabric workspace creation and pipeline deployment as human-only privileged actions.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **ADO Discussion Integration**: Loads the legacy `teams_integration` notification skill for writing ADO discussion updates.
- **Local LLM Integration**: Uses local authenticated CLIs to draft the implementation package.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Load Architecture Contract**: Uses the architecture, user stories, and at least 3 business input/output examples.
3. **Prepare Implementation Package**: Drafts proposed implementation steps for each user story flow-style specification.
4. **Mark Privileged Actions**: Records workspace creation and pipeline deployment as human-only actions.
5. **Request Approval**: Sends an approval request via Azure DevOps work item discussion.
6. **Move to Next Column**: Upon approval, moves the work item to the QA column.

## Configuration
Runtime columns, proposed workspace prefixes, approval polling settings, and pipeline names are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
