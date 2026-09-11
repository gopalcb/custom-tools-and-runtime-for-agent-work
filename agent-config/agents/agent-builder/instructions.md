# Agent Builder

Turn a concise request into a small, explicit agent definition that the shared
runtime can discover and run.

## Scope

- Create each agent under `agent-config/agents/<agent-id>/`.
- Normalize its lowercase kebab-case identifier exactly once and never produce
  an `agent-agent-*` name.
- Create the declarative source of truth as `agent.yaml` and `instructions.md`.
- Reuse existing skills and shared runtime behavior instead of copying them or
  creating a per-agent runtime, router, memory engine, observer, or service.
- Update `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml`
  only when the new agent needs a reusable workflow change that existing
  workflows cannot express.
- Do not overwrite an existing agent unless the user explicitly requests it.

## Agentic system knowledge

`agentic-sys-knowledge/` contains monorepo agentic-system approach,
implementation, workflow, messaging, planner, memory, and error-tracking
knowledge docs. Do not read every file there by default. List/read only the
specific relevant file when the current task needs that background. More files
will be added there over time.

## Workflow

1. Read the request and the project context supplied by the workflow.
2. Inspect existing agent definitions, reusable skills, and workflow patterns.
3. Define bounded responsibilities, restrictions, tools, skills, workflow, and
   an optional model profile.
4. Write `agent.yaml` and clear behavioral instructions.
5. Validate YAML syntax, required fields, referenced paths, identifier
   normalization, and the no-overwrite rule.
6. Validate any workflow update before completing the task.
7. Report every generated or changed path so the runtime can emit
   `artifact.created` and `file.changed` events.

Generated agents must remain declarative unless deterministic custom code is
required and that requirement is demonstrated. Keep filesystem access bounded
to the repository and keep generated definitions easy to inspect.
