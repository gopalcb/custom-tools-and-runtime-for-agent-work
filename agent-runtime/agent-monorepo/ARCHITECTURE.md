# Architecture

## Purpose

The shared runtime resolves declarative agents and workflows, executes them
through a Codex App Server client, publishes durable RuntimeEvent records,
exposes Codex slash-command requests, and finalizes run artifacts and
deterministic local work-memory candidates.

## Main Execution Flow

The project-scoped `bin/codex` shim passes through to the native Codex CLI.
The native CLI reads the repository `AGENTS.md` instructions for the default
interactive experience. The repository session-start hook runs the monorepo
system health check before starting companion services. The shared runtime
remains available for programmatic or App Server-backed workflows through
`bootstrap.initialize_project()` and the thin gateway.

The gateway delegates to AgentRuntime. The runtime uses Registry and Resolver
to select an agent and a fallback execution workflow. Before agent work starts,
it runs the mandatory monorepo system health check and records the result as a
`health.checked` RuntimeEvent. It then runs the planning workflow
(`pre-work-health`, `analyze`, `resolve-context`, optional `web-research`, and
`plan`) unless the user explicitly asked to skip planning, accepts a valid
planner workflow directive, persists any structured planner task breakdown
under `agent-runtime/controller-data-store/planned-tasks/`, and dispatches the
chosen execution workflow. The next agent step receives a planned-task handoff
that lists each generated `planned-task` identifier, and final reported
`planned-task <identifier>: <status>` lines update the matching task YAML
entries without interrupting the workflow.
`WorkflowEngine` handles agent, tool, shell, hook, and parallel steps. EventHub
persists and streams state; post_completion derives summaries, metrics,
artifacts, and memory candidates from those events. The shared file-backed
messaging bus stores agent communication under the configured
`.agent-state/agents-messaging` path.

Execution workflows run a strategy-feedback hook after their work steps and
before finalization when `memory.strategy_feedback.enabled` is true. That hook
launches the small Tkinter feedback tool, asks the
`strategy-memory-analyzer` agent to classify submitted feedback, stores
validated user-work-strategy memory records, falls back to local
feedback-derived memory when the analyzer stores nothing, and can run bounded
rework turns before asking for feedback again.

## Module Responsibilities

- `registry.py`: loads and validates project, agent, skill, and workflow YAML.
- `codex_launcher.py`: legacy project launcher that now passes through to
  native Codex.
- `resolver.py`: selects agents and assembles bounded project context.
- `workflow.py`: compatibility facade for workflow contracts and engine imports.
- `workflows/model.py`: defines workflow context, results, selection, and errors.
- `workflows/workflow_resolver.py`: expands catalog references, validates execution policy, and validates planner selection directives.
- `workflows/workflow_runner.py`: executes workflow control flow, retries, cancellation, events, and bounded parallel work.
- `runtime.py`: owns run lifecycle and step handlers.
- `system_health.py`: checks required monorepo services and writable state
  before work begins; unhealthy checks are reported to the messaging error
  tracker.
- `strategy_feedback.py`: launches the post-work feedback GUI, analyzes
  submitted feedback, and coordinates strategy-memory/rework decisions for the
  runtime hook.
- `planned_tasks.py`: writes implementation-plan task manifests and markdown
  files for controller visibility, renders planned-task handoffs, and updates
  linked task status.
- `task_runner.py`: CLI bridge for controller-created `task_request` messages;
  it marks task status, updates linked planned-task YAML when present, delegates
  execution to the runtime gateway, and replies through the message bus.
- `codex_client.py`: provides the official-SDK façade used by new integrations
  and the async App Server adapter used by gateway consumers.
- `logging_config.py`: configures Python application diagnostics in
  `.agent-state/logs/system/runtime/log-YYYY-MM-DD.log`.
- `events.py`: persists and streams the shared RuntimeEvent contract.
- `post_completion.py`: writes final artifacts from persisted events.
- `memory/`: derives deterministic event-based work-memory records and provides
  opt-in local lexical retrieval.
- `bootstrap.py`: constructs the application object graph, resolves the native
  Codex executable, starts optional background services such as the log analyzer,
  and exposes the project context used by runtime callers.

## Configuration

`project-registry.yaml`, `agent-config/agents/*/agent.yaml`,
`agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml`, and its
adjacent `workflow-steps.yaml` are the version-controlled sources of truth.
The orchestrator composes reusable catalog steps by `ref`; web research is
present only in the planning workflow.

Agent `model_profile` values resolve through the `model_profiles` section of
`project-registry.yaml`, which supplies Codex model and effort settings shared
by all agents that reference the same profile.

Memory is controlled by the `memory` section of `project-registry.yaml`.
When enabled, finalization writes run-scoped `memory_candidates.json` artifacts
and stores retrievable JSON records under `.agent-state/cache/memory/records/`.
Retrieval is local and lexical; no vector store or background scheduler is part
of this runtime.

Strategy feedback is controlled by `memory.strategy_feedback`. Submitted
feedback records are written as run artifacts, while accepted strategy memories
are stored under `.agent-state/cache/memory/records/strategy/` with active or
superseded status. The current request, current source tree, and agent
instructions remain more authoritative than retrieved strategy memory.

## Logging

RuntimeEvent records remain durable state under the configured `.agent-state`
tree. Normal Python diagnostics are configured on package import and during
bootstrap, then written to `.agent-state/logs/system/runtime/` with rotation.
Runtime error events are mirrored into `.agent-state/agents-messaging` as
`error.detected` messages, with the exact RuntimeEvent object used as the
message payload.

The optional `agent-config/agents/agent-logs-analyzer/log_analyzer.py` program is checked
during bootstrap. When present, it keeps one daemon thread running per project
root, tails fresh lines in `.agent-state/logs/system/**/*.log`, sends the exact
log error object to the shared message bus, updates
`.agent-state/agents-messaging/current-error.json`, and emits background
RuntimeEvents for detected `ERROR` entries.
