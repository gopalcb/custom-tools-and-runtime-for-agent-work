# Agentic Workflow End-to-End Working Process

## Purpose

This document describes the normal path from a user request to agent execution,
tracking, validation, memory, and operator visibility in this monorepo.

## Sources of Truth

Version-controlled configuration:

```text
project-registry.yaml
agent-config/agents/*/agent.yaml
agent-config/agents/*/instructions.md
agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml
agent-runtime/agent-monorepo/workflows/workflow-steps.yaml
```

Runtime state:

```text
.agent-state/logs/
.agent-state/sessions/
.agent-state/cache/memory/records/
.agent-state/agents-messaging/
```

The Python runtime owns execution. The Nest controller reads and writes
repository-backed state and launches task runner processes, but it does not own
workflow logic.

## Normal Request Flow

1. User submits a request through the runtime, gateway, or controller task UI.
2. Runtime emits `run.started`.
3. Resolver selects the agent and fallback execution workflow.
4. Runtime creates a `RunContext`.
5. Mandatory health check runs before agent work:

   ```text
   pre_work_health_check
   ```

6. Runtime emits `health.checked`.
7. If health is unhealthy, the run stops and the error is tracked through
   internal messaging.
8. If planning is not explicitly skipped, the planning workflow runs.
9. The planner may choose a specific execution workflow.
10. Runtime validates the chosen workflow id.
11. Runtime executes the selected workflow.
12. Runtime emits terminal state: `run.completed`, `run.failed`, or
    `run.cancelled`.
13. Finalization writes run artifacts and memory candidates.
14. Controller and work-log views project the persisted events and messages.

## Planning Workflow

Default planning sequence:

```text
pre-work-health -> analyze -> resolve-context -> optional web-research -> plan
```

The `resolve-context` step collects bounded repository context. The optional
`web-research` step runs only when the resolver decides current external facts
are required. The `plan` step invokes `agent-implementation-planner`, which must
return JSON matching `plan.schema.json`.

Planning can be skipped only when the user explicitly asks to skip planning.

## Execution Workflows

Execution workflows are declared in
`agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml`.

Each execution workflow now starts with:

```text
pre-work-health
```

Common default execution sequence:

```text
pre-work-health -> execute -> validate -> store-strategy-memory -> finalize
```

`finalize` is deferred until after the terminal run event so metrics, summaries,
artifacts, and memory candidates derive from the authoritative event stream.

## Agent Step Context Assembly

Before each Codex agent step, runtime assembles developer instructions from:

- selected agent instructions;
- allowed tool contract;
- validation commands;
- selected project context;
- retrieved project memory;
- internal messaging contract;
- selected skills;
- optional web research results for planning.

The agent step prompt contains the original user request and the current
workflow step. If planned tasks exist, the prompt includes a planned-task
handoff so implementation status can be reported back by identifier.

## Event Contract

`RuntimeEvent` is the live and durable state contract. Clients should consume
runtime state through EventHub/gateway streams or backend structured snapshots,
not by directly polling JSONL files from the browser.

Per-run events are persisted under:

```text
.agent-state/logs/<session-id>/<run-id>/events.jsonl
```

Final run artifacts are written beside the event stream:

```text
run.json
summary.md
metrics.json
artifacts.json
memory_candidates.json
```

## Messaging and Task Tracking

Controller-created tasks are represented as durable `task_request` messages.

Task flow:

1. Controller writes a pending message to:

   ```text
   .agent-state/agents-messaging/inbox/<agent-id>/
   ```

2. Controller writes a task record to:

   ```text
   .agent-state/agents-messaging/records/tasks/
   ```

3. Controller launches:

   ```bash
   .venv/bin/python -m agent_monorepo.task_runner
   ```

4. Task runner marks the task `implementing`.
5. Task runner delegates to the normal runtime gateway.
6. Task runner updates the task to `complete` or `need rework`.
7. Task runner sends a `task_request.result` reply.

The controller messaging portal, task thread, and work logs read the same
messaging records.

## Error Monitoring

Raw diagnostics are written under:

```text
.agent-state/logs/system/
```

The log analyzer watches `.agent-state/logs/system/**/*.log` for fresh `ERROR`
lines. For each detected error it builds an exact error object with:

- type;
- source;
- observed timestamp;
- relative log path;
- line number;
- exact log line;
- nearby context.

That object is passed to `MessageBus.record_error()`, which updates:

```text
.agent-state/agents-messaging/current-error.json
```

and sends an `error.detected` message with the exact object as payload.

Fixed and confirmed errors are archived under:

```text
.agent-state/agents-messaging/errors/
```

## Memory and Feedback

Finalization derives deterministic memory candidates from runtime events.
Accepted records are stored under:

```text
.agent-state/cache/memory/records/
```

Strategy feedback runs after execution work and before finalization when
enabled. The Tkinter feedback form captures user guidance, and accepted
strategy memory is stored under:

```text
.agent-state/cache/memory/records/strategy/
```

Future runs retrieve relevant active memory records and inject them under
`Retrieved project memory` in developer instructions.

## Health Check

The same health checker is available three ways:

- workflow hook: `pre_work_health_check`;
- runtime helper: `AgentRuntime._ensure_pre_work_health()`;
- CLI/program:

  ```bash
  .venv/bin/python -m agent_monorepo.system_health --project-root .
  ```

The session-start hook also runs:

```text
.codex/hooks/pre-work-health.py
```

Latest health output:

```text
.agent-state/logs/system/health/latest.json
```

## Validation

After runtime, workflow, agent, or Python changes:

```bash
.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-gateway agent-tools/internal-messaging agent-tools/ui-debugger agent-tools/strategy-feedback agent-config/agents/agent-implementation-planner agent-config/agents/agent-logs-analyzer
.venv/bin/python -m pytest -q
```

After controller changes:

```bash
cd agent-runtime/monorepo-controller
npm run backend:build
npm run build
```

After frontend behavior changes, run the controller and use the UI debugger
agent so screenshots, browser console errors, and failed XHR/fetch requests are
captured under `.agent-state/agents-messaging/debug-sessions/`.
