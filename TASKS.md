# Refined Agent Monorepo Implementation Tasks

Source: `refined-agent-monorepo-architecture-workflow-codex-console.md`

This plan implements the specification in dependency order. A task is complete only when its acceptance checks pass. The first validation gate must pass before implementation begins; the final validation gate must pass before `README.md` is written.

Supersession note: the root `agent-console/` Flask project and
`monorepo-agentic-dev` entry point have been removed. Current browser-control
work belongs under `agent-runtime/monorepo-controller/`, while the Python
runtime keeps the thin gateway and shared execution object graph.

## Execution rules

- Keep the gateway a one-file async facade and keep all execution ownership in the runtime.
- Keep agents declarative (`agent.yaml` and `instructions.md`) unless deterministic custom code is proven necessary.
- Keep workflow definitions beside the shared runtime and execute them with one
  compact engine.
- Use one `RuntimeEvent` contract for live UI state, append-only JSONL logs, metrics, artifacts, and finalization.
- Use Codex App Server JSON-RPC/JSONL as the structured execution boundary; never scrape human CLI output.
- Default local Codex runs to `approval_policy: never` and `sandbox: workspace-write`, so Codex can make in-workspace changes without prompting. Keep both values configurable.
- Preserve future memory directories as documentation/placeholders; do not create speculative providers, stores, schedulers, or a memory SDK.
- Do not add a Python/TypeScript bridge, HTTP service, general DAG system, or duplicate models/state stores.
- Handle task dependencies explicitly. Parallel work is allowed only for tasks whose listed dependencies are complete and whose files do not overlap.

## Validation gate 1 — specification coverage

- [x] V0.1 Independently compare every specification section (1–51), ownership matrix entry, implementation phase, anti-pattern, and definition-of-done item with this task list.
- [x] V0.2 Record omissions or ambiguities and update this file until the validator reports complete coverage.
- [x] V0.3 Do not begin implementation tasks until the independent validator gives a green signal.

## Phase 1 — structure and project configuration

- [x] T1.1 Create the specified root layout: `agent-gateway/`, `agent-runtime/agent-monorepo/__init__.py`, `agent-console/`, `tests/`, `docs/mockups/`, `agent-runtime/agent-monorepo/workflows/`, `agent-runtime/agent-monorepo/memory/ingestion/.gitkeep`, and root `.agent-state/{cache,logs,sessions}`.
  - Depends on: V0.3
  - Acceptance: directories match the recommended tree; placeholder `.gitkeep` files exist where required.
- [x] T1.2 Replace the fragmented Python packaging with one root `pyproject.toml` for Python 3.10+ and the minimal production dependencies PyYAML and Flask, plus test configuration.
  - Depends on: V0.3
  - Acceptance: one installable/runnable project config owns runtime, gateway, console, and tests; no separate gateway/runtime requirements remain.
- [x] T1.3 Refine `project-registry.yaml` into the repository-wide control-plane config with global paths, runtime defaults, Codex command/working directory/approval policy/sandbox, memory feature flags, and console enablement.
  - Depends on: V0.3
  - Acceptance: agents are not duplicated in the registry; discovery comes from `agents/*/agent.yaml`; default maximum parallel tasks is bounded.
- [x] T1.4 Move the HTML console mockup to `docs/mockups/codex-agent-console-ui-mockup.html` as a design reference and update `.gitignore` for root `.agent-state` while preserving placeholder files.
  - Depends on: V0.3
  - Acceptance: runtime logs, sessions, and cache content are ignored; declarative definitions and docs remain version controlled.
- [x] T1.5 Inventory obsolete duplicated control-plane/runtime layers, including the old packaged gateway internals, placeholder provider hierarchy, empty semantic runtime, and old state placement; map every retained behavior to its replacement owner without removing it yet.
  - Depends on: T1.1–T1.4
  - Acceptance: the removal inventory is complete enough for T12.1; no legacy behavior is lost accidentally during implementation.

## Phase 2 — declarative definitions and registry

- [x] T2.1 Convert `agent-builder` and `agent-ui-builder` to the declarative two-file pattern: `agent.yaml` plus `instructions.md`.
  - Depends on: T1.1, T1.3
  - Acceptance: each config has version, id, name, instructions path, workflow, skills, tools, and optional model profile; instruction files preserve bounded behavior and validation expectations.
- [x] T2.2 Add a minimal declarative `planner-agent` because workflows reference it.
  - Depends on: T1.1, T1.3
  - Acceptance: its scope is planning non-trivial multi-subsystem work only and it uses the same two-file pattern.
- [x] T2.3 Implement `registry.py` to load and validate project config, discover agent definitions, load instructions, load workflows, resolve skill paths, and cache parsed definitions.
  - Depends on: T1.3, T2.1, T2.2, T3.1
  - Acceptance: `get_agent`, `list_agents`, and `get_workflow` work; invalid/missing fields and escaping paths fail clearly; no separate loaders exist.

## Phase 3 — declarative workflows

- [x] T3.1 Create `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml` with `default` and `build-agent` workflows.
  - Depends on: T1.1
  - Acceptance: definitions cover context loading, conditional planning, conditional web research, resolved-agent execution, validation, optional UI work, and finalization using only `agent`, `tool`, `shell`, `hook`, and `parallel` primitives plus named `when`, `retry`, `timeout`, and `depends_on` controls.
- [x] T3.2 Implement `workflow.py` as one compact async engine for ordered steps, named conditions, dependencies, retry, timeouts, bounded parallel groups, hooks, and cancellation.
  - Depends on: T3.1, T4.1, T5.1
  - Acceptance: every attempt and state transition emits events; cancellation stops child tasks; user cancellation, invalid configuration, unchanged deterministic schema failures, and permission denial without changed permissions are never retried; there is no arbitrary expression language or general DAG/distributed scheduler.

## Phase 4 — unified events and run storage

- [x] T4.1 Implement `events.py` with the immutable `RuntimeEvent` contract and an `EventHub` that assigns per-run sequence numbers, appends and flushes JSONL immediately, publishes the same event to in-process subscribers, supports unsubscribe, and reloads run events.
  - Depends on: T1.1
  - Acceptance: concurrent emissions preserve ordering; a partially completed/crashed run leaves readable events; supported names include `run.started`, `run.completed`, `run.failed`, `run.cancelled`, `resolver.completed`, `workflow.started`, `workflow.completed`, `workflow.step.queued`, `workflow.step.started`, `workflow.step.progress`, `workflow.step.completed`, `workflow.step.failed`, `agent.started`, `agent.message.delta`, `agent.message.completed`, `agent.completed`, `tool.started`, `tool.completed`, `tool.failed`, `artifact.created`, `file.changed`, `background.started`, `background.progress`, `background.completed`, `background.failed`, and `error`, without event subclasses.
- [x] T4.2 Implement session/run storage under `.agent-state/logs/<session-id>/<run-id>/` and `.agent-state/sessions/<session-id>/session.json`.
  - Depends on: T4.1
  - Acceptance: paths cannot escape the state root; run metadata can be resumed; cache is used only for derived data.

## Phase 5 — deterministic resolver and context

- [x] T5.1 Implement `resolver.py` with `ResolvedRunSpec` and deterministic selection of agent, workflow, relevant skills/tools, planning flag, web-search flag, UI flag, context queries, named conditions, and verification commands.
  - Depends on: T2.1, T2.2, T3.1
  - Acceptance: explicit selection and aliases take priority; agent-building prompts select `agent-builder`; UI requests select/enable `agent-ui-builder`; trivial prompts avoid the planner; explicit research/current-information requests, potentially changed framework/library/API behavior, compatibility questions, required external specifications, unfamiliar third-party behavior, and implementation-relevant factual freshness enable web search; repository structure, local behavior/tests, project conventions, and facts already present in source/config/docs do not; the resolver decides once and agents do not independently repeat that decision; unresolved requests fail clearly or use a configured default.
- [x] T5.2 Implement `build_context_queries`, `collect_project_context`, and `compact_context` helpers near resolver/runtime using repository text search, configured-root path filtering, and bounded output suitable for one Codex turn.
  - Depends on: T5.1, T8.2
  - Acceptance: context follows source-of-truth priority, stays within configured roots, and does not introduce a separate context subsystem.

## Phase 6 — Codex App Server runtime

- [x] T6.1 Implement a testable async Codex App Server client in `runtime.py`, extracting `codex_client.py` when the documented size threshold is reached: launch `codex app-server`, perform initialize/initialized handshake, correlate JSON-RPC requests, start/resume threads, start turns, stream notifications, interrupt turns, and close cleanly.
  - Depends on: T4.1
  - Acceptance: command/config are injected; stderr is drained; protocol errors and early exits surface clearly; no visible-terminal parsing occurs; the adapter stays in `runtime.py` unless it crosses the documented split threshold.
- [x] T6.2 Normalize Codex thread/turn/item/delta/tool/file/diff/usage/error notifications into stable `RuntimeEvent` values.
  - Depends on: T6.1
  - Acceptance: the rest of the application does not depend on raw Codex field names; streamed text, code/diff data, tools, files, errors, and token usage are retained in stable payloads.
- [x] T6.3 Implement automatic local change authorization through configurable Codex settings, defaulting to `approvalPolicy: never` with workspace-write sandbox roots restricted to the repository.
  - Depends on: T6.1
  - Acceptance: normal in-repository file changes and commands do not pause for permission; configuration can opt into approval requests; any received approval request is normalized instead of hanging the client.
- [x] T6.4 Implement `RunContext` and `AgentRuntime` ownership of run/session IDs, resolution, context, workflow execution, child/background `asyncio.Task` handles, one run-level cancellation signal, lifecycle events, and final close/failure behavior.
  - Depends on: T2.3, T3.2, T4.2, T5.1, T5.2, T6.2, T8.1, T8.4
  - Acceptance: one runtime owns every transition; it supplies selected agent instructions, resolved skill references, permitted tools, model profile, compacted project context, and verification policy to each Codex turn; it dispatches tool requests through runtime-owned handlers and emits normalized events; background tasks emit start/progress/completion/failure; exceptions emit normalized errors and terminal run state; session resume is supported.
- [x] T6.5 Pin and document the supported Codex CLI/App Server protocol version or compatible version range and reject incompatible versions with a clear diagnostic.
  - Depends on: T6.1
  - Acceptance: the tested version policy is represented in project configuration/documentation and exercised without relying on human-readable Codex output for runtime state.

## Phase 7 — gateway and bootstrap

- [x] T7.1 Implement the one-file `agent-gateway/gateway.py` async facade returning an `AsyncIterator[RuntimeEvent]`, with run, session resume, and cancellation access needed by the console.
  - Depends on: T6.4
  - Acceptance: gateway delegates and contains no registry, resolution, execution, context, skills, provider, lifecycle, memory, or workflow logic.
- [x] T7.2 Implement `bootstrap.py` to locate the repository root, construct the registry, event infrastructure, memory service, resolver, workflow engine, Codex runtime client, runtime, and gateway without global singletons.
  - Depends on: T2.3, T3.2, T4.2, T5.1, T6.4, T7.1, T8.1
  - Acceptance: `bootstrap(project_root)` returns a working gateway and contains no business logic.

## Phase 8 — progressive memory and post-completion

- [x] T8.1 Implement `memory/service.py` with disabled-by-default retrieval/extraction policy and deterministic empty memory-candidate generation; document future ingestion behavior with a placeholder.
  - Depends on: T1.1
  - Acceptance: no LLM is called merely because a run completed; feature flags control behavior.
- [x] T8.2 Implement `memory/retrieval.py` with `MemoryHit`, safe path filtering, lexical matching, and metadata/recency weighting.
  - Depends on: T8.1
  - Acceptance: no embeddings/vector database/reranker is required; the interface can later add those stages.
- [x] T8.3 Add `memory/embeddings/README.md` and `memory/stores/README.md` documenting only the future protocols/adapters, with no empty provider/store Python classes or `agent-memory-sdk`.
  - Depends on: T1.1
- [x] T8.4 Implement `post_completion.py` to derive `run.json`, `summary.md`, metrics, `artifacts.json`, and `memory_candidates.json` from persisted events.
  - Depends on: T4.2, T8.1
  - Acceptance: artifact indexes come from `artifact.created`; metrics include durations, retries, tools, validation, file changes, and background tasks; disabled extraction still writes the documented contract; finalization does not collect a second raw-event stream.

## Phase 9 — browser console

- [x] T9.1 Build the static Flask template in `agent-console/templates/codex-agent-console.html` and `static/console.css` from the HTML reference: compact header/status bar, three-column workflow/activity/background workspace, prompt, and footer.
  - Depends on: T1.2, T1.4
  - Acceptance: styling follows the dark compact visual system and remains usable at practical terminal sizes; widget behavior stays in one file until the split threshold is earned.
- [x] T9.2 Connect browser prompt submission and the gateway event iterator through Flask/SSE; update only browser state from events.
  - Depends on: T7.2, T9.1
  - Acceptance: console does not poll JSONL, route agents, run workflow decisions, calculate final metrics, or own Codex session state.
- [x] T9.3 Map workflow/background/log/message/file/diff/artifact events to panels, progress indicators, status icons, and the activity stream.
  - Depends on: T9.2
  - Acceptance: queued/running/completed/failed states match the specification and streamed content appears live.
- [x] T9.4 Add web-server behavior and controls: `monorepo-agentic-dev`, `--agent`, `--session`, `--resume`, `--host`, `--port`, `--no-browser`, Enter, Shift+Enter, help, and cancellation.
  - Depends on: T9.2, T9.3
  - Acceptance: session resume and run cancellation work through runtime APIs.

## Phase 10 — Agent Builder and UI Builder end-to-end behavior

- [x] T10.1 Ensure the declarative Agent Builder workflow can generate the two-file agent pattern, validate required identifiers/instructions/skills/tools/workflow/paths, refuse accidental overwrite, and emit artifact events.
  - Depends on: T5.2, T6.4, T7.2, T8.4
  - Acceptance: generated definitions are discoverable immediately and no per-agent Python mini-application, separate eval file, or separate skill manifest is required; the builder may update `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml` when an agent needs a reusable workflow change, validates it, and emits artifact/file events for it.
- [x] T10.2 Ensure Agent UI Builder can produce lightweight HTML/CSS/small-JavaScript mockups under `artifacts/ui/` with `preview.json`, driven by its declarative instructions and shared runtime.
  - Depends on: T10.1
  - Acceptance: it remains a mockup generator, adds no frontend framework/runtime duplication, and the Flask browser console remains the production control-plane UI.

## Phase 11 — behavior-focused verification

- [x] T11.1 Add `tests/test_resolver.py` for deterministic routing, flags, skills/tools, context queries, validation profiles, and invalid configuration.
  - Depends on: T2.3, T5.1
- [x] T11.2 Add `tests/test_workflow_runtime.py` for ordering, conditions, dependencies, retries, timeouts, bounded parallel work, cancellation, background events, and failures.
  - Depends on: T3.2, T6.4
- [x] T11.3 Add `tests/test_events_and_finalization.py` for immediate JSONL durability, subscriber delivery, sequence ordering, reload, metrics, artifact indexes, summaries, and disabled memory candidates.
  - Depends on: T4.2, T8.4
- [x] T11.4 Add `tests/test_console_state.py` for event-to-view-state mapping and cancel/exit behavior without launching a real terminal.
  - Depends on: T9.4
- [x] T11.5 Add an integration smoke test using an injected fake Codex transport: prompt → resolver → workflow/events → streamed output → finalization → expected run artifacts.
  - Depends on: T7.2, T8.4, T9.2
- [x] T11.6 Run formatting/static checks if configured, the complete automated suite, import/compile checks, CLI help, and a fake-transport console/runtime smoke run.
  - Depends on: T11.1–T11.5
  - Acceptance: all checks pass without network access or a live Codex process.
- [x] T11.7 Where a compatible local Codex CLI is available, record its version and perform a bounded App Server handshake/protocol smoke test without starting a billable model turn.
  - Depends on: T6.1
  - Acceptance: lack of a local CLI is reported as an environmental limitation rather than hiding the result.

## Phase 12 — cleanup and architecture consistency

- [x] T12.1 Complete removal/merging from T1.5 and eliminate obsolete docs/configuration that contradict the refined architecture, while preserving useful behavioral instructions in their new owners.
  - Depends on: T10.2, T11.6
- [x] T12.2 Verify the final ownership matrix, source-of-truth ordering, compact-file thresholds, dependency direction, and absence of all listed anti-patterns.
  - Depends on: T12.1
- [x] T12.3 Verify all 14 initial definition-of-done observations, using the fake transport where a live Codex turn is unavailable.
  - Depends on: T12.2

## Validation gate 2 — implementation conformance

- [x] V2.1 Have an independent validator compare the final repository and test evidence against the source specification and every task/acceptance criterion above.
- [x] V2.2 Fix every material omission or mismatch and rerun affected verification until the validator gives a green signal.
- [x] V2.3 Do not write the final project `README.md` until the validator confirms architecture, behavior, and verification coverage.

## Phase 13 — intuitive project README

- [x] T13.1 Create root `README.md` only after V2.3, explaining the project purpose, mental model, request-to-completion flow, setup, console use, configuration, testing, extension points, current limitations, and source-of-truth rules.
- [x] T13.2 Include an intuitive project-tree architecture based on the refined specification and annotate each meaningful boundary without documenting removed legacy structure as current.
- [x] T13.3 Recheck all README commands and paths against the final repository.

## Final completion evidence

- [x] All implementation tasks and both validation gates are checked.
- [x] Test and smoke-check results are recorded in the delivery summary.
- [x] The repository starts from `monorepo-agentic-dev`, makes workspace changes without routine permission prompts under the configured local policy, streams one event model to the browser and disk, survives partial runs with event history, and derives final artifacts after completion.
