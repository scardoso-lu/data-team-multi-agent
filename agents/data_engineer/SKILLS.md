# Data Engineer Agent Skills

## Overview
The Data Engineer Agent is responsible for implementing the Medallion architecture on Microsoft Fabric. This agent operates in the **Engineering** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Commit data pipeline and transformation logic to the ADO Git repository.
  - Move work items to the next column (QA).

### 2. Teams Integration
- **Description**: Sends approval requests and notifications via Microsoft Teams.
- **Actions**:
  - Send approval requests for pipeline implementations.
  - Notify stakeholders of progress and approvals.

### 3. Fabric Integration
- **Description**: Interacts with Microsoft Fabric for data engineering tasks.
- **Actions**:
  - Create Fabric workspaces.
  - Deploy data pipelines for Bronze, Silver, and Gold layers.
  - Run dataflows in Fabric.

### 4. Medallion Architecture Implementation
- **Description**: Implements the Bronze, Silver, and Gold layers in Microsoft Fabric.
- **Actions**:
  - Ingest raw data into the Bronze layer.
  - Transform and clean data in the Silver layer.
  - Aggregate and enrich data in the Gold layer.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **Teams Integration**: Loads the `TeamsIntegration` skill for sending approval requests.
- **Fabric Integration**: Loads the `FabricIntegration` skill for interacting with Microsoft Fabric.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Implement Medallion Architecture**: Deploys pipelines for Bronze, Silver, and Gold layers in Microsoft Fabric.
3. **Commit Code**: Commits pipeline code to the ADO Git repository.
4. **Request Approval**: Sends an approval request via Microsoft Teams.
5. **Move to Next Column**: Upon approval, moves the work item to the QA column.

## Configuration
Runtime columns, workspace prefixes, approval callbacks, and pipeline names are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
- `azure-mgmt-fabric`: For interacting with Microsoft Fabric.
- `requests`: For sending HTTP requests to Microsoft Teams.
