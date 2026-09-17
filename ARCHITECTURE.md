# Custom Agent Tools and Runtime Architecture

`custom-agent-tools-and-runtime` is a compact, inspectable custom-agent runtime
and tool library extracted from the larger monorepo control plane. In this
checkout it currently lives under `my-system-libs/`. It keeps the essential
pieces in a small direct-folder layout so the system can be understood, copied,
committed, and tested without pulling in the full controller UI, full gateway,
or long-running agent runtime.

This is intentionally not a complete replacement for `agent-runtime/`. It is a
starter runtime and tool library for early work in the
`custom-agent-tools-and-runtime` repo.

## Design Goals

- Keep runtime behavior obvious from a small number of Python files.
- Prefer direct files and simple CLIs over nested package scaffolding.
- Keep state durable and inspectable under `.agent-state/`.
- Keep tools individually testable with local `test.py` files.
- Reuse source-of-truth workflow YAML concepts without importing the full
  monorepo gateway.
- Avoid speculative provider hierarchies, vector stores, schedulers, duplicate
  model layers, and Python/TypeScript bridge code.

## Top-Level Runtime

`runtime.py` is the compact facade. It loads sibling modules by path and exposes
`CompactAgentRuntime` for workflow resolution, dry-run execution, memory
store/search, MQ-style synchronous message dispatch, durable event-message
sending, and command-line usage.

`runtime_support.py` keeps runtime event and run context dataclasses out of the
facade so the main runtime file stays readable.

## Workflow

`workflow/engine.py` combines the useful parts of the full workflow resolver and
runner. It loads `workflow/yamls/workflow-orchestrator.yaml` and
`workflow/yamls/workflow-steps.yaml`, expands refs, validates dependency order,
supports conditions/retries/timeouts/cancellation, and can execute bounded
parallel groups.

Unsupported step types dry-run when handlers are not supplied. Callers can pass
handlers for real `agent`, `shell`, `tool`, `message`, `workflow`,
`controller`, or `hook` behavior.

## MQ Server

`mq_server/server.py` provides the compact FastAPI surface:

- `POST /messages`
- `GET /messages/{event_id}`
- `GET /messages`
- `GET /health`

Events are stored in memory for quick inspection and persisted through
`mq_server/store.py` under `.agent-state/messages/`. The background worker calls
`mq_server/handler.py`.

`mq_server/handler.py` supports task persistence, safe project file operations,
workflow resolution, memory operations, helper invocation, and system-error task
creation.

## Memory Server

`memory-server/server.py` writes deterministic JSON memory records below
`.agent-state/cache/memory/records/`. It rejects obvious secret assignments in
required text fields and ranks retrieval results with a compact lexical scorer.

## Agent Custom Tools

`agent-custom-tools/playwright-ui-testing/` owns persistent Chromium session
management, screenshot capture, short network tracing, console error capture,
and basic DOM hydration checks. Playwright imports lazily so non-browser tests
do not require installed browser binaries.

`agent-custom-tools/event-messaging/` owns durable file-backed messaging without
a nested package folder. It keeps inbox, processed, failed, records, tasks,
events, current-error, and archived-error state below one root.

`agent-custom-tools/strategy-feedback/` owns post-work feedback. It supports
fixture-driven collection, a Tkinter GUI, JSON analyzer parsing, local fallback
analysis, and memory-source metadata.

`agent-custom-tools/diagram-builder/` renders declarative YAML to HTML. It
supports copied flow/tree/event-bus/component-stack behavior plus the requested
compact component variants: horizontal right arrows, horizontal left arrows,
bidirectional arrows, animated horizontal arrows, square text nodes, square
icon/detail nodes, and node `icon`, `detail`, `size`, `color`, and `style`
options.

`sample-new-components.yaml` and `sample-new-components.html` are the visible
proof artifacts for those new diagram components.

`agent-custom-tools/knowledge-search/` separates web search, multi-question
research bundles, and local log search/error detection into three files plus a
dispatcher CLI.

## State Layout

The compact runtime uses the selected project root for state:

```text
.agent-state/
  agents-messaging/
  cache/memory/
  messages/
  strategy-feedback/
  playwright-ui-testing/
```

Tests prefer temporary directories so validation does not pollute the working
tree. Diagram generation is the exception: generated diagram samples are stored
beside their YAML sources when explicitly requested.

## Testing Contract

Every Python-bearing folder has a local `test.py`:

```bash
python test.py
python workflow/test.py
python mq_server/test.py
python memory-server/test.py
python agent-custom-tools/event-messaging/test.py
python agent-custom-tools/diagram-builder/test.py
python agent-custom-tools/knowledge-search/test.py
python agent-custom-tools/playwright-ui-testing/test.py
python agent-custom-tools/strategy-feedback/test.py
```

The tests are smoke-level by design. They avoid live browsers, live FastAPI
servers, live Codex calls, and persistent repository state unless a command is
explicitly generating a diagram artifact.

## Dependency Metadata

`requirements.txt` and `project.toml` list the compact project dependencies:
FastAPI/Pydantic for MQ, PyYAML for workflow and diagrams, Playwright for live
browser checks, and Uvicorn for serving the MQ API.
