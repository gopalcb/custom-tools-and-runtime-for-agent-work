# Monorepo Controller Architecture

## Purpose

`monorepo-controller` is the browser control surface for the local agent
monorepo. It shows available agents, skills, workflows, task threads, memory
records, work logs, and the transparent agent messaging portal. The former
Codex chat client and live Codex turn socket are intentionally removed from this
project.

## Three-part project structure

```text
monorepo-controller/
├── src/                         Angular presentation layer
│   └── app/                     Routed controller views and shared store
├── backend-api-services/        NestJS controller API
│   └── src/                     Repository-backed data services and routes
└── ../../agent-runtime/
    └── agent-monorepo/          Python runtime that owns execution and events
```

The ownership boundary is narrow:

1. Angular renders controller state, submits operator intent, and polls the
   backend snapshot API for refreshed state.
2. Nest reads and writes the monorepo's declarative files and durable local
   artifacts. It does not execute workflow logic itself.
3. The Python runtime still owns resolution, workflow execution, Codex App
   Server protocol, RuntimeEvent records, finalization, memory extraction, and
   task execution.

## Backend API

- `GET /api/controller/snapshot` returns all controller collections in one
  response for the shared Angular store.
- `GET /api/controller/agents` reads `agent-config/agents/*/agent.yaml` and instructions.
- `GET /api/controller/skills` reads `agent-config/skills/**/SKILL.md`.
- `POST /api/controller/skills` creates a new skill file and can append it to
  selected agent YAML definitions.
- `GET /api/controller/workflows` reads workflow YAML and expands step refs for
  display.
- `GET /api/controller/tasks` reads messaging task records, planned task
  manifests under `agent-runtime/controller-data-store/planned-tasks/`, and
  fallback tasks from RuntimeEvent run artifacts.
- `POST /api/controller/tasks` creates a `task_request` message, writes a task
  record, and starts the Python task runner.
- `GET /api/controller/memory` reads deterministic memory records from
  `.agent-state/cache/memory/records/`.
- `GET /api/controller/work-logs` projects runtime and messaging events into a
  compact timeline.
- `GET /api/controller/messaging` reads message records, message events, task
  status counts, the active operational error, and archived error records from
  `.agent-state/agents-messaging/`.
- `POST /api/controller/messages` sends an arbitrary message. UI debug requests
  to `agent-ui-debugger` also start one hub dispatch pass.
- `GET /api/controller/messaging/:messageId/thread` returns a message and its
  replies.
- `POST /api/sys-logs/browser` accepts browser runtime logs from Angular.

## Task Flow

Angular posts a task request to Nest. `MonorepoDataService` writes the pending
message under `.agent-state/agents-messaging/inbox/<agent>/`, indexes it under
`records/messages/`, appends `records/events.jsonl`, and writes
`records/tasks/<task>.json`. `TaskRunnerService` launches
`python -m agent_monorepo.task_runner`, which marks the task implementing,
streams the normal runtime workflow, finalizes runtime artifacts, updates the
task status, and sends a `task_request.result` reply.

Structured implementation plans also write tracked `planned-task` entries to
`agent-runtime/controller-data-store/planned-tasks/<plan-title>/`. Each
directory contains `tasks.yaml` plus one markdown file per planned task.
`MonorepoDataService` projects those YAML entries into the same task list used
by the Angular task thread. Runtime execution receives the generated task
identifiers in the next workflow step, and the Python task runner updates
linked YAML status as execution tasks move to implementing, complete, or need
rework.

## UI Debugger Flow

Requesters send a `ui_debug_request` message to `agent-ui-debugger`. The message
hub dispatches it to `agent-tools/ui-debugger`, which opens the URL with
Selenium, captures browser logs, filters Chrome DevTools network events to
actual failed fetch/XHR or document requests, saves a full-page screenshot, and
replies with compact counts and artifact paths.

## Configuration

`MONOREPO_ROOT` can override project-root discovery for the backend. `UI_ORIGIN`
is an optional comma-separated CORS allowlist. `SYS_LOG_DIR` can override the
backend sys-log directory; otherwise logs are created in
`.agent-state/logs/system/controller/`.

The Angular UI is served at `http://localhost:1001`. Its API URL defaults to
`http://localhost:1002`; set
`globalThis.__MONOREPO_BACKEND_URL__` before bootstrapping to override it.

The repository `.codex/hooks.json` invokes `.codex/hooks/start-controller.mjs`
on session start after `.codex/hooks/pre-work-health.py` confirms monorepo
system health. The controller startup hook serializes startup with a process
lock, checks HTTP readiness, and starts missing services as detached processes.
Startup output is stored under `.agent-state/logs/controller/startup/`; process
state lives under `.agent-state/cache/controller/`. These low ports require OS
permission on systems that restrict ports below 1024.
