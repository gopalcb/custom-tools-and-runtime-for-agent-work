# Monorepo Architecture

This repository is a local Codex agent control plane. The native Codex CLI is
the default terminal interface. The shared runtime, gateway, controller,
declarative agents, workflows, events, finalization artifacts, and deterministic
work memory are one system.

The `agent-monorepo` agent owns the project as a full-stack steward. It should
understand how frontend controller behavior, backend API services, Python
runtime execution, declarative agent configuration, workflow YAML, local tools,
tests, docs, and native Codex subagents fit together. Its job is to keep the
system coherent, detect drift, and make scoped changes that preserve the
existing architecture.

```text
.
├── AGENTS.md
│   Repository-level instructions for Codex and native subagents.
├── project-registry.yaml
│   Global source of truth for agent/config paths, runtime defaults, Codex
│   policy, memory feature flags, and validation commands.
├── pyproject.toml
│   Editable Python package wiring for runtime, gateway, messaging, and UI
│   debugger modules.
├── bin/
│   Native Codex passthrough wrapper. Keep this thin.
├── .codex/
│   Native Codex local config and custom subagent TOML files.
│
├── agent-config/
│   ├── agents/
│   │   ├── agent-monorepo/
│   │   │   Default project specialist for this repository.
│   │   ├── codex-agent/
│   │   │   Generic fallback used when a request starts with `/codex-agent`.
│   │   ├── agent-builder/
│   │   │   Declarative agent design and creation agent.
│   │   ├── agent-ui-builder/
│   │   │   Lightweight UI mockup agent.
│   │   ├── agent-ui-debugger/
│   │   │   Agent wrapper for browser/debugger checks.
│   │   ├── agent-implementation-planner/
│   │   │   Read-only planner agent plus its CLI, schema, and validation code.
│   │   └── agent-logs-analyzer/
│   │       Optional background log analyzer program and instructions.
│   ├── skills/
│   │   Reusable SKILL.md instruction packages referenced by agent YAML.
│   └── context/
│       Agent-facing project context documents, including this file.
│
├── agent-runtime/
│   ├── agent-monorepo/
│   │   ├── bootstrap.py
│   │   │   Finds the project root, loads the registry, resolves native Codex,
│   │   │   builds the gateway/runtime object graph, and starts optional
│   │   │   background services.
│   │   ├── registry.py
│   │   │   Loads and validates project-registry.yaml, agent.yaml files, skills,
│   │   │   workflow YAML, defaults, aliases, and safe paths.
│   │   ├── resolver.py
│   │   │   Selects agents/workflows, detects planning and web research needs,
│   │   │   resolves validation commands, and gathers bounded project context.
│   │   ├── runtime.py
│   │   │   Owns run lifecycle, workflow step handlers, Codex turns, commands,
│   │   │   sessions, approvals, cancellation, and event emission.
│   │   ├── codex_client.py
│   │   │   Async Codex App Server adapter plus SDK-style helper client.
│   │   ├── events.py
│   │   │   RuntimeEvent contract, subscribers, append-only event storage, run
│   │   │   directories, and session metadata.
│   │   ├── post_completion.py
│   │   │   Derives summaries, metrics, artifact indexes, and memory candidates
│   │   │   from persisted events.
│   │   ├── task_runner.py
│   │   │   Executes controller-created task_request messages through the shared
│   │   │   runtime and writes message/task replies.
│   │   ├── memory/
│   │   │   Deterministic event-derived work-memory extraction and lexical
│   │   │   retrieval. Durable records live under `.agent-state/cache/memory/`.
│   │   └── workflows/
│   │       YAML workflow sources plus resolver/runner/model code.
│   └── monorepo-controller/
│       Angular/Nest operator dashboard. It displays and edits repository-backed
│       agent, skill, workflow, task, memory, work-log, and messaging state.
│
├── agent-gateway/
│   Thin public facade over the shared runtime. Keep routing, workflow logic,
│   event derivation, and memory behavior in agent-runtime/agent-monorepo.
│
├── agent-tools/
│   ├── internal-messaging/
│   │   File-backed message bus under `.agent-state/agents-messaging`.
│   ├── ui-debugger/
│   │   Selenium-based browser verification and artifact capture.
│   └── web-search/
│       External research helper used only when planning requires current facts.
│
├── .agent-state/
│   Local derived state. Runtime logs, sessions, messaging records, plans, and
│   memory records are not configuration.
│
├── docs/
│   Usage notes and design plans. Prefer current source and registry values when
│   docs disagree.
└── tests/
    Offline Python tests using fake Codex transports.
```

Core flow:

```text
user request
  -> AgentGateway
  -> Registry + Resolver
  -> planning workflow when not skipped
  -> selected execution workflow
  -> Codex App Server and local tools
  -> RuntimeEvent stream
  -> .agent-state/logs/<session>/<run>/
  -> post-completion artifacts and optional memory records
```

Sources of truth:

- `project-registry.yaml` defines configured roots and runtime policy.
- `agent-config/agents/*/agent.yaml` defines agent identity, workflow, tools,
  skills, aliases, and model profile.
- `agent-config/agents/*/instructions.md` defines agent behavior.
- `agent-config/skills/**/SKILL.md` defines reusable agent instructions.
- `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml` and
  `workflow-steps.yaml` define orchestration.
- `RuntimeEvent` in `agent-runtime/agent-monorepo/events.py` is the shared
  state contract for clients, finalization, metrics, artifacts, and memory.

Agent model:

- Agent = who owns durable work and produces an outcome.
- Skill = reusable knowledge, procedure, rules, examples, or validation
  criteria that can be shared by multiple agents.
- Tool = something an agent can operate, such as shell, repo, web search,
  messaging, Selenium, or the Codex App Server.
- Workflow = the ordered execution policy for planning, implementation,
  validation, and finalization.
- Temporary subagent = bounded worker for exploration, testing, review,
  debugging, or independent side work. The owner agent keeps final
  responsibility for decisions, edits, validation, and user-facing summaries.
- Context = repository knowledge loaded progressively from current source,
  architecture docs, code maps, tests, memory, and runtime evidence.

Drift checks for the owner agent:

- Registry paths should match the actual `agent-config/` layout.
- Agent YAML, instructions, declared skills, workflows, and resolver behavior
  should describe compatible responsibilities.
- Controller backend reads/writes should use configured roots and must not
  recreate stale top-level configuration directories.
- Runtime events, finalization artifacts, memory records, and controller views
  should rely on the shared RuntimeEvent contract instead of parallel state
  formats.
- Python projects with structure changes should keep `ARCHITECTURE.md` and
  `code-map.yaml` synchronized.
- Validation commands in `project-registry.yaml`, `AGENTS.md`, docs, and native
  Codex subagent TOML should stay aligned.

Boundaries:

- Keep the gateway thin.
- Keep clients on structured backend/runtime APIs. Do not make clients poll
  JSONL logs or duplicate runtime state.
- Keep new agents declarative unless deterministic Python is clearly required.
- Keep durable run artifacts under `.agent-state/logs/<session>/<run>/`.
- Keep deterministic memory under `.agent-state/cache/memory/records/`.
- Do not add speculative provider hierarchies, vector stores, schedulers,
  duplicate model layers, or Python/TypeScript bridges.
