# Architecture

## Purpose

The shared runtime resolves declarative agents and workflows, executes them through a Codex App Server client, publishes durable RuntimeEvent records, exposes Codex slash-command requests, and finalizes run artifacts and optional memory candidates.

## Main Execution Flow

The gateway delegates to AgentRuntime. The runtime uses Registry and Resolver to select an agent and a fallback execution workflow. It then runs the planning workflow (`analyze`, `resolve-context`, optional `web-research`, and `plan`), accepts a valid planner workflow directive, and dispatches the chosen execution workflow. `WorkflowEngine` handles agent, tool, shell, hook, and parallel steps. EventHub persists and streams state; post_completion derives summaries and metrics from those events. The shared file-backed messaging bus stores agent communication under the configured `.agent-state/agents-messaging` path.

## Module Responsibilities

- `registry.py`: loads and validates project, agent, skill, and workflow YAML.
- `resolver.py`: selects agents and assembles bounded project context.
- `workflow.py`: compatibility facade for workflow contracts and engine imports.
- `workflows/model.py`: defines workflow context, results, selection, and errors.
- `workflows/workflow_resolver.py`: expands catalog references, validates execution policy, and validates planner selection directives.
- `workflows/workflow_runner.py`: executes workflow control flow, retries, cancellation, events, and bounded parallel work.
- `runtime.py`: owns run lifecycle and step handlers.
- `codex_client.py`: provides the official-SDK façade used by new integrations
  and the async App Server adapter used by gateway consumers.
- `events.py`: persists and streams the shared RuntimeEvent contract.
- `post_completion.py`: writes final artifacts from persisted events.
- `memory/`: provides opt-in deterministic local retrieval.
- `bootstrap.py`: constructs the application object graph.

## Configuration

`project-registry.yaml`, agent YAML files,
`agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml`, and its
adjacent `workflow-steps.yaml` are the version-controlled sources of truth.
The orchestrator composes reusable catalog steps by `ref`; web research is
present only in the planning workflow.
