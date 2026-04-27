# Data Analyst Agent Skills

## Overview
The Data Analyst Agent is responsible for developing semantic models and Power BI artifacts based on the Gold layer. This agent operates in the **Analytics** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Update the ADO Wiki with data dictionaries and documentation.
  - Move work items to the next column (Governance).

### 2. Teams Integration
- **Description**: Sends approval requests and notifications via Microsoft Teams.
- **Actions**:
  - Send approval requests for semantic models and Power BI artifacts.
  - Notify stakeholders of progress and approvals.

### 3. Purview Integration
- **Description**: Interacts with Microsoft Purview for data governance.
- **Actions**:
  - Publish metadata and data dictionaries to Microsoft Purview.
  - Ensure compliance with data governance policies.

### 4. Semantic Modeling
- **Description**: Develops semantic models and Power BI artifacts.
- **Actions**:
  - Design semantic models based on the Gold layer.
  - Create data dictionaries and documentation.
  - Develop Power BI reports and dashboards.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **Teams Integration**: Loads the `TeamsIntegration` skill for sending approval requests.
- **Purview Integration**: Loads the `PurviewIntegration` skill for interacting with Microsoft Purview.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Develop Semantic Model**: Designs semantic models based on the Gold layer schema.
3. **Publish Metadata**: Publishes metadata and data dictionaries to Microsoft Purview.
4. **Update Wiki**: Documents data dictionaries and semantic models in the ADO Wiki.
5. **Request Approval**: Sends an approval request via Microsoft Teams.
6. **Move to Next Column**: Upon approval, moves the work item to the Governance column.

## Configuration
Runtime columns, approval callbacks, and sample semantic model output are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
- `azure-purview-scanning`: For interacting with Microsoft Purview.
- `requests`: For sending HTTP requests to Microsoft Teams.
