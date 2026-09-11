# How End-to-End Agents Internal Messaging Works

## Purpose

Internal messaging is the repository-backed coordination layer for agents and
the controller UI. It is intentionally file-backed so agent requests, replies,
task status, error alerts, and UI debugger artifacts remain inspectable after a
process exits.

Use message passing when one agent needs another agent or tool to act, when the
operator UI needs transparent state, or when an error must remain visible until
it is confirmed fixed.

## Durable Location

Default root:

```text
.agent-state/agents-messaging/
```

The root can be overridden with `AGENT_MESSAGING_ROOT` or the `agent-msg
--root` option.

Current layout:

```text
.agent-state/agents-messaging/
  inbox/<agent-id>/
  processed/<agent-id>/
  failed/<agent-id>/
  records/messages/<message-id>.json
  records/tasks/<task-id>.json
  records/events.jsonl
  current-error.json
  errors/<error-id>.json
  debug-sessions/<request-id>/
  manifest.json
```

`manifest.json` describes the durable contract. `records/events.jsonl` is the
append-only event stream for message, task, and error lifecycle events.

## Core Code Paths

- Message bus:
  `agent-tools/internal-messaging/agents_internal_messaging/bus.py`
- CLI:
  `agent-tools/internal-messaging/agents_internal_messaging/cli.py`
- Optional polling hub:
  `agent-tools/internal-messaging/agents_internal_messaging/hub.py`
- Controller projection:
  `agent-runtime/monorepo-controller/backend-api-services/src/monorepo-data.service.ts`
- Angular view:
  `agent-runtime/monorepo-controller/src/app/components/messaging-portal/`

## Message Lifecycle

1. A sender creates an `AgentMessage` with sender, recipient, type, payload,
   and optional `reply_to`.
2. `MessageBus.send()` writes the message atomically to:

   ```text
   inbox/<recipient>/<timestamp>-<message-id>.json
   ```

3. The same message is indexed under:

   ```text
   records/messages/<message-id>.json
   ```

4. A `sent` event is appended to:

   ```text
   records/events.jsonl
   ```

5. A handler, hub, or agent reads pending inbox files.
6. On success, `mark_processed()` moves the inbox file to `processed/<agent-id>/`
   and updates the record status.
7. On failure, `mark_failed()` moves the file to `failed/<agent-id>/`, writes a
   sibling `.error.txt`, updates the record, and appends a failed event.
8. Replies are normal messages with `reply_to` set to the original message id.

## Agent-Facing CLI

Send a message:

```bash
PYTHONPATH=agent-tools/internal-messaging \
  .venv/bin/python -m agents_internal_messaging.cli send \
  --sender agent-monorepo \
  --recipient agent-ui-debugger \
  --type ui_debug_request \
  --payload-json '{"url":"http://localhost:1001","request_id":"manual-check"}'
```

Inspect state:

```bash
agent-msg list --json
agent-msg events --limit 20
agent-msg tasks --json
agent-msg current-error --json
agent-msg errors --json
```

Resolve the current operational error after confirming the fix:

```bash
agent-msg resolve-error --details-json '{"confirmed_by":"operator","evidence":"tests passed"}'
```

## Runtime Injection

Before every Codex agent step, `AgentRuntime._assembled_instructions()` adds an
`Agent messaging` section to the developer instructions. It tells the active
agent that `agent-msg` is available, gives the sender id, points to the durable
messaging root, and includes the pending inbox count for that agent.

Agents should send compact messages. Large artifacts such as screenshots,
browser logs, or long debug outputs should be stored under
`.agent-state/agents-messaging/...` and referenced by path.

## Controller and UI

The Nest controller reads the same files and exposes them through:

```text
GET /api/controller/messaging
GET /api/controller/messaging/:messageId/thread
POST /api/controller/messages
```

The Angular messaging portal displays:

- message totals and task totals;
- pending, processed, and failed message records;
- recent lifecycle events;
- active and archived operational errors;
- UI debugger request controls.

The browser does not parse JSONL files directly. It receives structured
snapshots from the backend.

## Error Messaging

Operational errors use the same bus. `MessageBus.record_error()` stores or
updates `current-error.json`, sends an `error.detected` message whose payload is
the exact error object, and appends an error lifecycle event.

If a new different error arrives while another active error exists, the old one
is archived as `superseded` under `errors/`. When the current error is fixed and
confirmed, `resolve_current_error()` moves it to `errors/` with status `fixed`.

## Validation

Use these checks after messaging changes:

```bash
.venv/bin/python -m compileall agent-tools/internal-messaging agent-runtime/agent-monorepo
.venv/bin/python -m pytest -q tests/test_internal_messaging_bus.py tests/test_internal_messaging_cli.py
cd agent-runtime/monorepo-controller && npm run backend:build && npm run build
```
