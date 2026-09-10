# Monorepo Controller

Local Angular/Nest control surface for streamed Codex SDK turns.

## Run locally

From the repository root, use three terminals:

```bash
.venv/bin/python agent-tools/codex-sdk-client/api.py --cwd . --port 8770
.venv/bin/python agent-tools/ui-debugger/api.py --port 8771
cd agent-runtime/monorepo-controller && npm run backend:build && npm run backend:start
```

In a fourth terminal, serve the Angular UI:

```bash
cd agent-runtime/monorepo-controller && npm start
```

The UI is normally served at `http://localhost:4200`; the Nest API binds to
`http://127.0.0.1:3000`. Submit a prompt in the chat panel. The REST request
starts one SDK turn and the Socket.IO `/codex` namespace displays its live SDK
agent, tool, and file-change notifications.

## Verification

```bash
npm run backend:build
npm run build
```

The backend is designed to be testable with an HTTP replacement for
`UI_DEBUGGER_API_URL`; it does not require a logged-in Codex instance to
compile.
