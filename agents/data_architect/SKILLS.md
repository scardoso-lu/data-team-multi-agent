# Data Architect Agent Skills

## Overview
The Data Architect Agent is responsible for translating business requirements into data models and scaffolding the initial architecture. This agent operates in the **Architecture** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Update the ADO Wiki with architecture documentation.
  - Move work items to the next column (Engineering).

### 2. Teams Integration
- **Description**: Sends approval requests and notifications via Microsoft Teams.
- **Actions**:
  - Send approval requests for architecture designs.
  - Notify stakeholders of progress and approvals.

### 3. Architecture Design
- **Description**: Translates business requirements into data models.
- **Actions**:
  - Design database schemas and relationships.
  - Document architecture decisions in the ADO Wiki.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **Teams Integration**: Loads the `TeamsIntegration` skill for sending approval requests.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Design Architecture**: Translates business requirements into data models and updates the ADO Wiki.
3. **Request Approval**: Sends an approval request via Microsoft Teams.
4. **Move to Next Column**: Upon approval, moves the work item to the Engineering column.

## Configuration
Runtime columns, approval callbacks, and sample architecture output are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
- `requests`: For sending HTTP requests to Microsoft Teams.
