# Internal Messaging Architecture

`agents_internal_messaging` is the shared file-backed message bus for every
agent, including Codex agents. Messages are written atomically to
`.agent-state/agents-messaging/inbox/<recipient>/`, then indexed under
`records/messages/` and appended to `records/events.jsonl`. Processed and
failed messages remain durable in their corresponding folders.

The `agent-msg` CLI is the supported agent-facing interface. `agent-hub`
provides optional polling and handler dispatch. The root may be overridden by
`AGENT_MESSAGING_ROOT` for tests or isolated runs.
