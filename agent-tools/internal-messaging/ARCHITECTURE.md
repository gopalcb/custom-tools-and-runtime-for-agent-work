# Internal Messaging Architecture

`agents_internal_messaging/` is the shared file-backed message bus for every
agent, including Codex agents. Messages are written atomically to
`.agent-state/agents-messaging/inbox/<recipient>/`, then indexed under
`records/messages/` and appended to `records/events.jsonl` with payload and
lifecycle details. Processed and failed messages remain durable in their
corresponding folders.

The message root is self-describing. `manifest.json` names every durable folder,
`records/tasks/` stores controller-created task records linked to
`task_request` messages and runtime runs, `current-error.json` stores the active
operational error when one exists, `errors/` archives fixed or superseded
operational errors, and `debug-sessions/` stores UI debugger screenshots,
console logs, network errors, and manifests.

The `agent-msg` CLI is the supported agent-facing interface. It can send,
inspect, list threads, show task records, read the append-only messaging event
log, inspect the active operational error, list archived errors, and resolve the
current error after a fix is confirmed. `agent-hub` provides optional polling
and handler dispatch, including the deterministic `agent-ui-debugger` handler.
Python source lives directly under this project root in
`agents_internal_messaging/` rather than a nested `src/` layout. The root may be
overridden by `AGENT_MESSAGING_ROOT` for tests or isolated runs.

Python diagnostics are written to
`.agent-state/logs/system/messaging/log-YYYY-MM-DD.log`. The durable message
event stream remains under the configured message root at `records/events.jsonl`.
