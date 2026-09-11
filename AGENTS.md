# Agent Monorepo Guidance

This repository is a local Codex-powered agent control plane. Use the native
Codex CLI as the default terminal experience. The root `bin/codex` wrapper, when
present on `PATH`, must pass through to the native CLI and must not launch a
custom terminal UI.

## Project agent routing

- Default to the dedicated `agent-monorepo` behavior for this repository. Treat
  the local runtime, workflow YAML, agent definitions, event contract,
  finalization artifacts, and work-memory behavior as one system.
- If the user starts a request with `/codex-agent`, switch to the generic
  `codex-agent` behavior in `agent-config/agents/codex-agent/instructions.md` for that
  request.
- Run the planning workflow first for normal requests: `analyze`,
  `resolve-context`, optional `web-research`, and `plan`. Bypass it only when
  the user explicitly asks to skip planning.
- Use web research only when the request needs current or external facts.
  Prefer primary sources and cite them in user-facing answers when used.

## Agentic system knowledge

- `agentic-sys-knowledge/` contains monorepo agentic-system approach,
  implementation, workflow, messaging, planner, memory, and error-tracking
  knowledge docs.
- Do not read every file in `agentic-sys-knowledge/` by default. Treat it as an
  opt-in knowledge base: read the specific file only when it is relevant to the
  current task, when architecture/process context is needed, or when the user
  asks about those systems.
- More files will be added there over time, so check the directory listing when
  a task needs agentic-system background before assuming the current set is
  complete.

## Native Codex subagent routing

- Use the `standard` subagent for ordinary non-trivial repository engineering
  tasks: normal bugs, features, API/frontend/backend changes, focused
  refactors, test failures, and known-subsystem debugging.
- Use the `deep` subagent for architecture changes, cross-system failures,
  authentication/security issues, migrations, difficult incidents, major
  refactors, or state/concurrency problems.
- Keep the main thread responsible for final decisions, edits, validation, and
  user-facing summary unless the user explicitly asks for parallel execution.

## Project sources of truth

- Treat `project-registry.yaml`, `agent-config/agents/*/agent.yaml`, each agent's
  `instructions.md`, and
  `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml` with its
  adjacent `workflow-steps.yaml` as the version-controlled sources of truth.
- Keep the gateway thin. Resolution, planning, execution, Codex App Server
  protocol, workflow state, events, finalization, and memory access belong to
  `agent-runtime/agent-monorepo/`.
- Use the shared `RuntimeEvent` contract for live client state, artifacts,
  metrics, summaries, and memory candidates. Never make clients poll JSONL logs
  or duplicate runtime state.
- Store durable run artifacts under `.agent-state/logs/<session>/<run>/`.
  Deterministic work-memory records are derived from those events and stored
  under `.agent-state/cache/memory/records/` when memory extraction is enabled.
- Keep new agents declarative. Add custom Python only for proven deterministic
  behavior that the shared runtime and YAML workflow cannot express.
- Keep Codex changes inside the configured workspace-write roots. The local
  default approval policy is `never`, so normal in-repository work should not
  pause for permission prompts.
- After runtime, workflow, agent, or Python changes, run
  `.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-gateway agent-tools/internal-messaging agent-tools/ui-debugger agent-config/agents/agent-implementation-planner agent-config/agents/agent-logs-analyzer`
  and `.venv/bin/python -m pytest -q`.
- Use fake Codex transports for automated tests. Do not require a live Codex
  session for normal unit or integration tests.
- Do not add speculative provider hierarchies, vector stores, schedulers,
  duplicate model layers, or a Python/TypeScript bridge.

## Python projects

Whenever you create, review, refactor, or extend Python code, read and follow
`agent-config/skills/python-coder/SKILL.md` before editing. Keep each Python project
documented with `ARCHITECTURE.md` and `code-map.yaml`, keep those files in sync
with Python structure changes, and run the relevant compile and test checks.
