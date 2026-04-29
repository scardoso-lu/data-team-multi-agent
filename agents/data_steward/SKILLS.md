# Data Steward Agent Skills

## Overview
The Data Steward Agent acts as the final gatekeeper for data governance and compliance. This agent operates in the **Governance** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Audit the ADO Git repository and Wiki for compliance.
  - Move work items to the **Done** column.

### 2. ADO Discussion Integration
- **Description**: Writes notifications and summaries to Azure DevOps work item discussion.
- **Actions**:
  - Post final summaries and compliance reports to Azure DevOps work item discussion.
  - Notify stakeholders of work item completion.

### 3. Purview Integration
- **Description**: Interacts with Microsoft Purview for data governance.
- **Actions**:
  - Audit metadata and compliance in Microsoft Purview.
  - Ensure end-to-end data governance and compliance.

### 4. Governance and Compliance
- **Description**: Performs final governance reviews and compliance checks.
- **Actions**:
  - Verify business input/output examples were preserved and used as acceptance evidence.
  - Audit the entire data lifecycle for compliance.
  - Validate end-to-end data flows and governance.
  - Post final summaries to Azure DevOps work item discussion.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **ADO Discussion Integration**: Loads the legacy `teams_integration` notification skill for writing ADO discussion updates.
- **Purview Integration**: Loads the `PurviewIntegration` skill for interacting with Microsoft Purview.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Audit Lifecycle**: Audits the entire data lifecycle for compliance and governance.
3. **Publish Metadata**: Publishes final metadata and compliance reports to Microsoft Purview.
4. **Post Summary**: Posts a final summary to Azure DevOps work item discussion.
5. **Mark as Done**: Marks the work item as **Done** in the ADO board.

## Configuration
Runtime columns, completion notifications, and sample governance audit results are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
- `azure-purview-scanning`: For interacting with Microsoft Purview.
