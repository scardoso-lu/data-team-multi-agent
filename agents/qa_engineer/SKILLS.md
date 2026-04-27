# QA Engineer Agent Skills

## Overview
The QA Engineer Agent is responsible for evaluating data quality and testing frameworks on Microsoft Fabric. This agent operates in the **QA** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Update the ADO Wiki with test coverage plans and results.
  - Move work items to the next column (Analytics).

### 2. Teams Integration
- **Description**: Sends approval requests and notifications via Microsoft Teams.
- **Actions**:
  - Send approval requests for data quality checks.
  - Notify stakeholders of progress and approvals.

### 3. Fabric Integration
- **Description**: Interacts with Microsoft Fabric for data quality checks.
- **Actions**:
  - Run data quality checks on Fabric pipelines.
  - Validate data integrity and consistency.

### 4. Data Quality and Testing
- **Description**: Evaluates data quality and testing frameworks.
- **Actions**:
  - Run data quality checks on Bronze, Silver, and Gold layers.
  - Document test coverage and results in the ADO Wiki.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **Teams Integration**: Loads the `TeamsIntegration` skill for sending approval requests.
- **Fabric Integration**: Loads the `FabricIntegration` skill for interacting with Microsoft Fabric.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Run Data Quality Checks**: Evaluates data quality for Bronze, Silver, and Gold layers.
3. **Update Wiki**: Documents test coverage and results in the ADO Wiki.
4. **Request Approval**: Sends an approval request via Microsoft Teams.
5. **Move to Next Column**: Upon approval, moves the work item to the Analytics column.

## Configuration
Runtime columns, approval callbacks, pipeline names, and sample quality results are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
- `azure-mgmt-fabric`: For interacting with Microsoft Fabric.
- `requests`: For sending HTTP requests to Microsoft Teams.
