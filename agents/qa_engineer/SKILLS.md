# QA Engineer Agent Skills

## Overview
The QA Engineer Agent is responsible for evaluating data quality and acceptance criteria from reviewed implementation artifacts. This agent operates in the **QA** column of the Azure DevOps (ADO) Kanban board and does not run Fabric platform actions.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Update the ADO Wiki with test coverage plans and results.
  - Move work items to the next column (Analytics).

### 2. ADO Discussion Integration
- **Description**: Writes approval requests and status updates to Azure DevOps work item discussion.
- **Actions**:
  - Send approval requests for data quality checks.
  - Notify stakeholders of progress and approvals.

### 3. Data Quality and Testing
- **Description**: Evaluates data quality and testing frameworks.
- **Actions**:
  - Use the business input/output examples as required acceptance tests.
  - Prepare Bronze, Silver, and Gold validation checks for human-reviewed outputs.
  - Document test coverage and results in the ADO Wiki.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **ADO Discussion Integration**: Loads the legacy `teams_integration` notification skill for writing ADO discussion updates.
- **Local LLM Integration**: Uses local authenticated CLIs to draft acceptance checks.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Load Acceptance Examples**: Uses at least 3 business input/output examples from Engineering.
3. **Prepare Data Quality Checks**: Evaluates expected results for Bronze, Silver, and Gold outputs.
4. **Update Wiki**: Documents test coverage and results in the ADO Wiki.
5. **Request Approval**: Sends an approval request via Azure DevOps work item discussion.
6. **Move to Next Column**: Upon approval, moves the work item to the Analytics column.

## Configuration
Runtime columns, approval polling settings, pipeline names, and sample quality results are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
