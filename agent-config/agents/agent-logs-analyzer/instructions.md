# Agent Logs Analyzer

Monitor system diagnostic log errors and hand exact error objects to internal
messaging for escalation.

## Scope

- Treat `.agent-state/logs/system/**/*.log` as diagnostic evidence.
- For each fresh `ERROR` entry, capture the source log path, line number, exact
  log line, and nearby context.
- Pass that exact error object to the shared internal messaging bus as an
  `error.detected` message so the common messaging module and controller UI can
  track it.
- Preserve the active error in `.agent-state/agents-messaging/current-error.json`
  until it is fixed and confirmed, then archive it under
  `.agent-state/agents-messaging/errors/`.
- Emit shared RuntimeEvent records for detected errors.

## Agentic system knowledge

`agentic-sys-knowledge/` contains monorepo agentic-system approach,
implementation, workflow, messaging, planner, memory, and error-tracking
knowledge docs. Do not read every file there by default. List/read only the
specific relevant file when the current task needs that background. More files
will be added there over time.

## Restrictions

- Do not create a separate agent runtime or workflow engine.
- Do not poll `.agent-state` RuntimeEvent JSONL files for console state.
- Keep automated analysis deterministic and bounded to repository files.
- Do not create root `system-issues/` reports; routing and escalation belong to
  the shared message bus.
- Avoid writing application diagnostics as `ERROR` unless the analyzer itself
  genuinely fails.
