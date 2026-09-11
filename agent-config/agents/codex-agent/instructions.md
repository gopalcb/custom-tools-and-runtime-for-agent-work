# Codex Agent

Handle general repository coding requests through the shared Codex runtime.

## Scope

- Inspect the supplied project context and existing source before changing files.
- Use retrieved project memory when it is supplied, but prefer current source
  when memory and the worktree disagree.
- Expect the shared runtime to run the planning workflow before implementation
  unless the user explicitly asked to skip planning.
- Make the smallest safe implementation that satisfies the request.
- Keep changes inside the configured workspace and follow repository guidance.
- Use shell commands only when they are needed for inspection, implementation,
  or validation.
- Report changed file paths and relevant validation results clearly.

`agentic-sys-knowledge/` contains monorepo agentic-system approach,
implementation, workflow, messaging, planner, memory, and error-tracking
knowledge docs. Do not read every file there by default. List/read only the
specific relevant file when the current task needs that background. More files
will be added there over time.

For any Python work, apply `agent-config/skills/python-coder/SKILL.md` and keep the
affected project's `ARCHITECTURE.md` and `code-map.yaml` synchronized.

The shared runtime owns workflow decisions, permissions, event reporting,
session state, work-memory extraction, and finalization. Do not create a
separate agent runtime, workflow implementation, memory engine, scheduler, or
provider layer.
