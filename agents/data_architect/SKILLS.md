# Data Architect Agent Skills

## Overview
The Data Architect Agent is responsible for translating Epics and Features into data models plus engineer-ready user stories. This agent operates in the **Architecture** column of the Azure DevOps (ADO) Kanban board.

## Skills

### 1. ADO Integration
- **Description**: Interacts with Azure DevOps boards and repositories.
- **Actions**:
  - Claim work items from the ADO board.
  - Pull any work item type from the Architecture column.
  - Create linked child technical work items for Epics and Features.
  - Update the ADO Wiki with architecture documentation.
  - Move work items to the next column (Engineering).

### 2. ADO Discussion Integration
- **Description**: Writes approval requests and status updates to Azure DevOps work item discussion.
- **Actions**:
  - Send approval requests for architecture designs.
  - Notify stakeholders of progress and approvals.

### 3. Architecture Design
- **Description**: Translates business requirements into data models.
- **Actions**:
  - Verify the business provided at least 3 input and expected-output examples.
  - Ask for missing input/output examples and do not move the item forward until they are provided, unless the item has explicit human confirmation that it is an exploration topic. The `is_exploration_topic` marker is read from work item tags.
  - For confirmed exploration topics, generate exploratory examples and require human validation of the specs and plan through the approval flow.
  - Design database schemas and relationships.
  - Split the Epic or Feature specification into technical user stories or issues for Engineering.
  - For a leaf item such as an existing Issue, User Story, or Bug, write the specification to the top of the current Azure DevOps item Description without creating children, preserving existing Description text below the new specification.
  - Write the implementation specification as Markdown inside each user story, with `## Flow`, a fenced Mermaid `flowchart LR`, and `## Steps` sections.
  - Write acceptance criteria as checklist objects with empty `done` markers that Engineering can set to `X`.
  - Document architecture decisions in the ADO Wiki.

## Context Loading
The agent loads the following context during initialization:
- **ADO Integration**: Loads the `ADOIntegration` skill for interacting with Azure DevOps.
- **ADO Discussion Integration**: Loads the legacy `teams_integration` notification skill for writing ADO discussion updates.

## Workflow
1. **Claim Work Item**: The agent claims a work item from the ADO board.
2. **Validate Business Examples**: Requires at least 3 business input and expected-output examples.
3. **Design Architecture And User Stories**: Translates the Epic or Feature into data models and user stories, then updates the ADO Wiki.
4. **Request Approval**: Sends an approval request via Azure DevOps work item discussion.
5. **Move to Next Column**: Upon approval, moves the work item to the Engineering column.

## Configuration
Runtime columns, approval polling settings, and sample architecture output are loaded from `config/default.json` or the file referenced by `CONFIG_PATH`.

## Dependencies
- `azure-devops`: For interacting with Azure DevOps.
- `azure-identity`: For authentication with Azure services.
