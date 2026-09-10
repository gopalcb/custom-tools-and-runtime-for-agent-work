# Agents Internal Messaging

Local, lightweight file-backed messaging for Codex agents.

The package provides:

- `agent-msg` for sending requests between local agents;
- `agent-hub` / `agent_hub.py` for polling agent inboxes and dispatching handlers;
- a built-in handler for `ui_debug_request` messages addressed to
  `angular-ui-debugger-agent`;
- per-sender reply messages that contain concise result summaries and artifact
  paths, avoiding large screenshots or logs in model context.
- durable message records under `records/messages/` plus an append-only
  `records/events.jsonl` log for human inspection and UI integration.

Messages default to `.agent-state/agents-messaging` in the current repository.
Override with `AGENT_MESSAGING_ROOT` or `--root`.

The built-in UI debug handler expects `angular-ui-debugger` to be installed in
the same Python environment, or available on `PYTHONPATH` in a source checkout.

## Example

```bash
agent-msg send \
  --sender builder-agent \
  --recipient angular-ui-debugger-agent \
  --type ui_debug_request \
  --payload-file debug-request.json

agent-msg list --json
agent-msg summary
agent-msg show <message-id>
agent-msg thread <message-id>

agent-hub run-once
```

From this monorepo without installing:

```bash
PYTHONPATH=agents-internal-messaging/src:angular-ui-debugger/src \
  python3 -m agents_internal_messaging.hub listen
```

The hub writes processed messages under `processed/` and replies under the
sender inbox.

The bus also maintains a visibility index:

```text
.agent-state/agents-messaging/
  inbox/<agent-id>/
  processed/<agent-id>/
  failed/<agent-id>/
  records/messages/<message-id>.json
  records/events.jsonl
```

Use `agent-msg list` for a compact terminal view or `agent-msg list --json` as
the easiest integration point for local dashboards such as Agent Builder.

The Python program uses the permissions of the process that starts it. It does
not elevate filesystem or browser-launch permissions.
