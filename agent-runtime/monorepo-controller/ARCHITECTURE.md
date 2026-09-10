# Monorepo Controller Architecture

## Purpose

`monorepo-controller` is the browser control surface for a local Codex SDK
turn. Its routed Agent client starts a turn, carries the unchanged Codex SDK
event log to the browser in real time, and retains a small reconnect buffer
per turn.

## Three-part project structure

```text
monorepo-controller/
├── src/                         Angular presentation layer
│   └── app/                     Views, store, HTTP client, Socket.IO client
├── backend-api-services/        NestJS transport layer
│   └── src/                     REST controller and reusable event gateway
└── ../../agent-tools/           Local Codex integration layer
    ├── codex-sdk-client/api.py  SDK process and raw NDJSON Codex event source
    └── ui-debugger/api.py       Stable debugger proxy used by Nest
```

The three parts have deliberately narrow ownership:

1. Angular renders state and sends user intent; the `agent-client` route is
   the dedicated console UI and does not parse files or connect to Codex
   directly.
2. Nest owns HTTP commands and the reusable Socket.IO fan-out service.
3. The Python tools own SDK lifecycle and the debugger-facing HTTP contract.

Application runtime logs are separate from agent interaction logs. Browser,
Nest, and other controller application events are written under
`sys-logs/log-yyyy-mm-dd.log` using:

```text
<datetime> - <application name/path/to/file> - <label> - <log message>
```

`ApplicationLogService` owns the file format and daily log files. Angular
installs `BrowserLoggingService` at bootstrap to forward console calls,
framework errors, unhandled promise rejections, failed `fetch` calls, and
failed XHR requests to the backend logging endpoint.

## Live event flow

```text
Angular POST /api/codex/turns
  -> Nest CodexController
  -> CodexApiClientService
  -> ui-debugger /v1/turns
  -> codex-sdk-client /v1/turns
  -> Codex SDK

Codex SDK NDJSON notifications
  -> ui-debugger passthrough
  -> Nest CodexEventsGateway (one reader per turn)
  -> Socket.IO /codex room turn:<id>
  -> Angular CodexRealtimeService
```

The raw stream is intentionally not terminal-scraped or transformed into a
second log format. The event gateway packages each notification with its turn
id, keeps the most recent 500 events for a reconnecting socket, and signals
completion after the stream closes.

The broader agent runtime continues to own durable `RuntimeEvent` records for
workflow runs. This controller is the SDK-client control surface and never
polls runtime JSONL files.

## Agent client UI

`/agent-client` replaces the former persistent chat sidebar. It presents the
Codex turn API as a dedicated workflow, activity, background-task, and prompt
workspace. The component derives display state only from events received via
`CodexRealtimeService`; the Nest API remains the sole HTTP and real-time
transport boundary.

## Backend API

- `GET /api/codex/health` checks the debugger and SDK service chain.
- `POST /api/codex/turns` starts a turn and begins the single stream reader.
- `GET /api/codex/turns/:turnId` returns the reconnect buffer.
- `POST /api/codex/turns/:turnId/steer` forwards additional user input.
- `POST /api/codex/turns/:turnId/interrupt` forwards cancellation.
- `POST /api/sys-logs/browser` accepts browser console, runtime, fetch, and
  XHR error logs and appends them to `sys-logs/log-yyyy-mm-dd.log`.
- Socket namespace `/codex` accepts `codex.subscribe` with `{ turnId }` and
  emits `codex.ready`, `codex.event`, and `codex.completed`.

## Configuration

`UI_DEBUGGER_API_URL` configures Nest's debugger API (default
`http://127.0.0.1:8771`). `CODEX_SDK_API_URL` configures the debugger's SDK
API (default `http://127.0.0.1:8770`). `UI_ORIGIN` is an optional
comma-separated CORS allowlist. Angular defaults to `http://127.0.0.1:3000`;
set `globalThis.__MONOREPO_BACKEND_URL__` before bootstrapping to override it.
`SYS_LOG_DIR` can override the backend log directory; otherwise logs are
created in `monorepo-controller/sys-logs/`.
