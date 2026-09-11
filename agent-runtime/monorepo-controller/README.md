# Monorepo Controller

Local Angular/Nest control surface for the agent monorepo.

## Run locally

From the repository root, build and start the backend:

```bash
cd agent-runtime/monorepo-controller && npm run backend:build && npm run backend:start
```

In another terminal, serve the Angular UI:

```bash
cd agent-runtime/monorepo-controller && npm start
```

The UI is normally served at `http://localhost:1001`; the Nest API binds to
`http://localhost:1002`.

The controller reads agents, skills, workflows, task records, memory records,
work logs, and messaging records from the monorepo. Creating a task writes a
`task_request` message under `.agent-state/agents-messaging/` and launches the
Python runtime task runner. Sending a `ui_debug_request` to
`agent-ui-debugger` launches one message-hub dispatch pass and stores Selenium
artifacts under `.agent-state/agents-messaging/debug-sessions/`.

## Verification

```bash
npm run backend:build
npm run build
```

The backend and frontend compile without requiring a live Codex task. Runtime
task execution is covered by Python tests with fake Codex transports.

## Codex session startup

The repository `.codex/hooks.json` runs `.codex/hooks/start-controller.mjs` on
session start. Review and trust the hook with `/hooks` in Codex once, then start
or resume a session. Install dependencies with `npm ci` in this directory first.
The hook checks both services, builds the backend when it needs starting, and
starts missing services as detached processes. A startup lock prevents duplicate
launches from concurrent sessions. Existing healthy services are reused.

To start immediately from the repository root:

```bash
node .codex/hooks/start-controller.mjs
```

Startup logs are in `.agent-state/logs/controller/startup/`; service PID files
and the transient startup lock are in `.agent-state/cache/controller/`.
Services stay running when the Codex session ends. To stop a service, send TERM
to the PID in its `frontend.pid` or `backend.pid` file after verifying the PID
still belongs to that service. Restart services after changing their startup
configuration; the hook does not restart healthy processes.

Ports 1001 and 1002 are below 1024. On systems that restrict these ports,
startup reports `EACCES` until the operating system permits binding them.
The hook does not elevate privileges or silently substitute other ports.
