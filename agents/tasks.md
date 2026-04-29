# Agent LLM Tasks

Task prompts loaded at runtime by `agents/task_loader.py` via `load_task(key)`.
Each `##` heading is a task key that matches the agent's `agent_key`.
Edit the text under each heading to change what is sent to the LLM; keep
the heading names and file location stable so the loader can find them.

## data_architect

Design a data architecture contract for downstream engineering and QA.
If the source work item is an Epic or Feature, split its specification
into engineer-ready child user stories or issues depending on the ADO
process. If the source work item is already a User Story or Issue,
create the specification on that item without child work items. Each
story/specification must include title, user_story, specification,
acceptance_criteria, and business_io_examples.
Write the specification as Markdown in this exact style: start with
'## Flow', include plain-language context, include a fenced Mermaid
'flowchart LR' process graph, then include '## Steps' with numbered
operational descriptions and branch conditions. Do not write generic
Bronze/Silver/Gold filler unless the work item explicitly requires those
layers. If source, target, rules, or ownership are not available, write
'Insufficient information available.' for that missing part instead of
inventing details. Make acceptance_criteria a checklist list where each
item has done and item fields. Use done='' for incomplete items so
Engineering can later mark done='X'. Use the business input/output
examples as acceptance goals.

## data_engineer

Create a reviewable implementation package for Fabric Bronze, Silver,
and Gold pipelines. Do not create workspaces, deploy pipelines, run
dataflows, or mutate cloud resources. Use the business input/output
examples as acceptance goals for the human engineer. Implement from the
engineer-ready user stories, where each story contains its specification.

## qa_engineer

Create QA acceptance checks from the business input/output examples.
Each check must trace to at least one expected output.

## data_analyst

Develop a semantic model and metric definitions for analytics.
Use the business input/output examples as expected analytical results.

## data_steward

Review the lifecycle artifact for governance, compliance, security,
and production-data safety. Return a governance audit result.
