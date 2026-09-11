# Agent Monorepo Usage

## What This Framework Is

This monorepo is a local Codex-powered agent control plane. The native Codex CLI
remains the default terminal experience, while the repository provides:

- declarative agents under `agent-config/agents/*/agent.yaml`;
- stable agent instructions beside each agent in `instructions.md`;
- shared workflows under `agent-runtime/agent-monorepo/workflows/`;
- durable runtime events under `.agent-state/logs/<session>/<run>/`;
- deterministic local memory under `.agent-state/cache/memory/records/`;
- transparent agent messaging under `.agent-state/agents-messaging/`;
- an Angular/Nest controller UI under `agent-runtime/monorepo-controller/`.

Use the controller when you want an operator dashboard. Use the CLI/runtime when
you want direct agent execution or automation.

## Start The Controller

From the repo root:

```bash
cd agent-runtime/monorepo-controller
npm run backend:build
npm run backend:start
```

In another terminal:

```bash
cd agent-runtime/monorepo-controller
npm start
```

The backend defaults to `http://localhost:1002`; Angular defaults to
`http://localhost:1001`. If 1001 is busy:

```bash
npm start -- --host 127.0.0.1 --port 4201
```

The controller routes are:

- `Task thread`: create tasks, assign agents, and watch status update.
- `Monorepo agents`: inspect discovered agents, tools, skills, workflow, and
  recent message history.
- `Workflows`: inspect orchestration YAML and resolved step lists.
- `Memory system`: review deterministic memory records from completed runs.
- `Work logs`: review runtime and messaging activity in one timeline.
- `Agent messaging portal`: inspect messages, send messages, and trigger UI
  debugger checks.

## Create And Run A Task

Open `Task thread`, switch to `Task config`, choose an agent, and submit a
prompt. The controller writes:

```text
.agent-state/agents-messaging/inbox/<agent-id>/<message>.json
.agent-state/agents-messaging/records/messages/<message-id>.json
.agent-state/agents-messaging/records/tasks/<task-id>.json
.agent-state/agents-messaging/records/events.jsonl
```

Then it launches:

```bash
.venv/bin/python -m agent_monorepo.task_runner
```

The runner marks the task `implementing`, delegates to the normal shared
runtime, updates the task to `complete` or `need rework`, and sends a
`task_request.result` reply message back to `monorepo-controller`.

Automated tests use fake Codex transports. A real task run needs a compatible
native Codex CLI and whatever account/session setup your local CLI requires.

## Use Agent Messaging

Send a message from the terminal:

```bash
PYTHONPATH=agent-tools/internal-messaging \
  .venv/bin/python -m agents_internal_messaging.cli send \
  --sender agent-monorepo \
  --recipient agent-ui-debugger \
  --type ui_debug_request \
  --payload-json '{"url":"http://127.0.0.1:1001","request_id":"home-check"}'
```

Inspect records:

```bash
PYTHONPATH=agent-tools/internal-messaging \
  .venv/bin/python -m agents_internal_messaging.cli list --json

PYTHONPATH=agent-tools/internal-messaging \
  .venv/bin/python -m agents_internal_messaging.cli events --limit 20

PYTHONPATH=agent-tools/internal-messaging \
  .venv/bin/python -m agents_internal_messaging.cli tasks --json
```

The controller's messaging portal shows the same records. Messages stay durable
after processing or failure, and the root `manifest.json` documents the folder
contract.

## Use The UI Debugger Agent

Install Selenium in the venv if needed:

```bash
.venv/bin/python -m pip install -r agent-tools/ui-debugger/requirements.txt
```

Send a debug request through the controller's Agent messaging portal or with
`agent-msg`, then dispatch once:

```bash
PYTHONPATH=agent-tools/internal-messaging:agent-tools/ui-debugger \
  .venv/bin/python -m agents_internal_messaging.hub run-once
```

A successful run writes:

```text
.agent-state/agents-messaging/debug-sessions/<request-id>/
├── manifest.json
├── screenshot.png
├── console.json
└── network-errors.json
```

The debugger captures browser console logs and filters Chrome DevTools network
events to actionable failures: failed fetch/XHR requests, failed document loads,
HTTP error statuses, and `Network.loadingFailed` entries. It does not inline
large screenshots or request/response bodies in messages.

You can also run it directly:

```bash
PYTHONPATH=agent-tools/internal-messaging:agent-tools/ui-debugger \
  .venv/bin/python -m ui_debugger.cli http://127.0.0.1:1001 --request-id manual-check
```

## Add Skills From The UI

Open `Monorepo agents -> Skills` or `Skills`, then create a skill with a
kebab-case id. The backend writes:

```text
agent-config/skills/<category>/<skill-id>/SKILL.md
```

If you select agents during creation, the backend appends the new skill id to
their `agent.yaml` files. Duplicate skill ids are rejected so the registry does
not become ambiguous.

## Review Memory

Memory records are deterministic JSON files derived from RuntimeEvents, not
model-written summaries. Review them in `Memory system` or directly under:

```text
.agent-state/cache/memory/records/<session-id>/<run-id>/*.json
```

Useful memory records are ones that change future behavior: architectural
decisions, stable failure patterns, workflow constraints, and verified project
facts. Stale environment failures should be treated cautiously.

## Inspect Work Logs

`Work logs` combines:

- runtime event summaries from `.agent-state/logs/**/events.jsonl`;
- message and task events from `.agent-state/agents-messaging/records/events.jsonl`.

The browser does not poll JSONL files directly. It asks the backend for
structured summaries, keeping file parsing and path safety in the server.

## Validate The Monorepo

For Python/runtime changes:

```bash
.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-gateway agent-tools/internal-messaging agent-tools/ui-debugger agent-config/agents/agent-implementation-planner agent-config/agents/agent-logs-analyzer
.venv/bin/python -m pytest -q
```

For the controller:

```bash
cd agent-runtime/monorepo-controller
npm run backend:build
npm run build
```

For UI verification, run the controller and send a `ui_debug_request` to
`agent-ui-debugger`. A clean pass should report `console_error_count: 0` and
`network_issue_count: 0`.

## Good Operating Habits

- Keep agents declarative unless a deterministic tool is clearly needed.
- Keep the gateway thin; execution, events, workflow state, finalization, and
  memory belong to `agent-runtime/agent-monorepo/`.
- Use message passing for cross-agent requests so the full interaction is
  inspectable later.
- Store large artifacts as files and send paths in reply messages.
- Prefer fake Codex transports in tests and reserve live Codex runs for manual
  smoke checks.
- Use the UI debugger after frontend changes; it catches console/CORS/network
  failures that a production build cannot see.

## References

- Selenium browser logs and WebDriver behavior: https://www.selenium.dev/documentation/webdriver/
- Selenium Chrome options and capabilities: https://www.selenium.dev/documentation/webdriver/browsers/chrome/
- Chrome DevTools Protocol Network events: https://chromedevtools.github.io/devtools-protocol/tot/Network/
