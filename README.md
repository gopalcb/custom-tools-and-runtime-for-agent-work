# Codex Agent Monorepo

This repository is a compact local control plane for specialized coding
agents. The native Codex CLI remains the default terminal experience; the
shared Python runtime is available for App Server-backed workflows, durable
events, finalization artifacts, local work memory, and gateway consumers.

The design keeps each source of truth easy to find:

- agent identity and capabilities live in `agent-config/agents/*/agent.yaml`;
- agent behavior lives beside it in `instructions.md`;
- orchestration lives with the shared runtime in
  `agent-runtime/agent-monorepo/workflows/`, composed from its reusable step
  catalog;
- global paths and runtime policy live in `project-registry.yaml`;
- Python owns execution, events, storage, memory, and the gateway-facing runtime.

## How a request runs

```text
prompt
  │
  ▼
Gateway consumer ──► AgentGateway ──► deterministic Resolver
                                         │
                                         ▼
                         planning workflow → YAML WorkflowEngine
                                         │
                         ┌───────────────┼────────────────┐
                         ▼               ▼                ▼
                   project context  Codex App Server  validation
                         │               │                │
                         └───────────────┼────────────────┘
                                         ▼
                                  RuntimeEvent stream
                                           │
                                           ▼
                                      events.jsonl
                                           │
                                           ▼
                               post-completion artifacts
```

The resolver uses explicit, deterministic rules first. Every catalog-enabled run starts with analysis and project context; optional web research is limited to that planning phase. The planner can choose only a declared execution workflow, and the workflow engine handles ordered and conditional steps, retries, timeouts, dependencies, bounded parallel validation, and cancellation.

Codex notifications are normalized at the runtime boundary. Gateway consumers and persisted logs therefore use stable `RuntimeEvent` fields instead of raw App Server protocol objects. Events are appended and flushed as work happens, so an interrupted process still leaves useful history.

## Project architecture

```text
.
├── project-registry.yaml                 # Global paths, limits, Codex policy, feature flags
├── pyproject.toml                        # Python package wiring and CLI commands
├── AGENTS.md                             # Repository guidance for coding agents
│
├── agent-config/                         # Declarative agent configuration
│   ├── context/
│   │   └── monorepo-architecture.md      # Compact agent-facing architecture map
│   ├── skills/                           # Reusable instruction files selected by the resolver
│   └── agents/                           # Declarative agent definitions
│       ├── agent-monorepo/
│       │   ├── agent.yaml                # Default project specialist
│       │   └── instructions.md
│       ├── agent-builder/
│       │   ├── agent.yaml                # Routing, workflow, skills, tools, model profile
│       │   └── instructions.md           # How to create and validate new agents
│       ├── agent-ui-builder/
│       │   ├── agent.yaml
│       │   └── instructions.md           # Lightweight HTML/CSS/JS mockup behavior
│       ├── agent-ui-debugger/
│       │   ├── agent.yaml
│       │   └── instructions.md
│       ├── agent-implementation-planner/
│       │   ├── agent.yaml
│       │   ├── instructions.md           # Read-only implementation planning contract
│       │   ├── planner.py                # Standalone structured planner CLI
│       │   ├── validation.py
│       │   └── plan.schema.json
│       ├── agent-logs-analyzer/
│       │   ├── agent.yaml
│       │   └── instructions.md
│       └── codex-agent/
│           ├── agent.yaml                # Generic fallback selected by /codex-agent
│           └── instructions.md
│
├── agent-gateway/
│   └── gateway.py                        # Thin public run/resume/cancel/approval facade
│
├── agent-runtime/
│   ├── agent-monorepo/
│   │   ├── bootstrap.py                  # Builds the application object graph
│   │   ├── registry.py                   # Loads and validates config, agents, skills, workflows
│   │   ├── resolver.py                   # Produces one deterministic executable run spec
│   │   ├── runtime.py                    # Owns runs, Codex turns, tools, sessions, cancellation
│   │   ├── codex_client.py               # Async Codex App Server JSONL/JSON-RPC adapter
│   │   ├── workflow.py                   # Compatibility facade for workflow imports
│   │   ├── workflows/                    # Models, resolver, runner, and workflow YAML
│   │   │   ├── workflow-orchestrator.yaml # Planning and execution composition
│   │   │   └── workflow-steps.yaml        # Reusable declarative step catalog
│   │   ├── events.py                     # Immutable events, subscribers, append-only storage
│   │   ├── post_completion.py            # Derives summaries, metrics, artifacts, memory candidates
│   │   └── memory/
│   │       ├── service.py                # Memory policy and deterministic candidate output
│   │       ├── retrieval.py              # Safe lexical retrieval with metadata/recency weighting
│   │       ├── ingestion/.gitkeep        # Reserved ingestion boundary
│   │       ├── embeddings/README.md      # Future embedding protocol, no premature provider code
│   │       └── stores/README.md          # Future store protocol, no premature adapter code
│   └── monorepo-controller/              # Angular/Nest browser control surface
├── agent-tools/
│   ├── web-search/                         # Codex SDK-backed external research
│   └── internal-messaging/                 # Durable agent-to-agent message bus
│
├── .agent-state/                         # Local derived state; contents are ignored by Git
│   ├── cache/
│   ├── logs/<session>/<run>/             # events.jsonl and derived run artifacts
│   └── sessions/<session>/session.json   # Resume metadata and Codex thread ID
│
├── docs/                                 # Design notes, memory plans, improvement backlog
└── tests/                                # Resolver, workflow, events, protocol, integration
```

The gateway stays small so another interface can wrap the same runtime later. Interfaces send user actions through the gateway; they do not route agents, interpret workflows, poll log files, or calculate final metrics.

All agents receive the shared `agent_messaging` capability. Use `agent-msg` to
send and inspect messages; records are stored in `.agent-state/agents-messaging`.

## Requirements and setup

Use Python 3.10 or newer and a Codex CLI compatible with the configured App
Server range. The current registry accepts `>=0.153.4,<0.155.0`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
codex --version
```

The browser controller is maintained under `agent-runtime/monorepo-controller`.
Run its Nest backend and Angular frontend as described in that project's README:

```bash
cd agent-runtime/monorepo-controller
```

Codex commands are kept out of workflow execution. `/models` queries the App
Server model list; `/status`, `/help`, `/interrupt`, and `/compact` are also
forwarded immediately through the structured command bridge.

The implementation planner can also be run directly without changing the
repository:

```bash
python agent-config/agents/agent-implementation-planner/planner.py \
  "Plan the requested repository change" --repo . --dry-run
```

## Local change and approval policy

The default `project-registry.yaml` configuration uses:

```yaml
codex:
  approval_policy: never
  sandbox: workspace-write
  writable_roots:
    - .
```

This lets Codex make ordinary changes inside this repository without stopping for permission. Writable roots are validated to remain inside the configured project root.

To require decisions, change `approval_policy` to an App Server opt-in policy such as `on-request`. Gateway consumers can surface pending requests and call `respond_to_approval(request_id, decision)`.

## Runtime output

Each run writes continuously to:

```text
.agent-state/logs/<session-id>/<run-id>/
├── events.jsonl
├── run.json
├── summary.md
├── metrics.json
├── artifacts.json
└── memory_candidates.json
```

`events.jsonl` is the append-only factual record. Finalization derives every other file from those events. `artifacts.json` indexes `artifact.created` events, while session metadata retains the Codex thread ID needed by `--resume`.

Memory is progressive. Deterministic extraction and local lexical retrieval are
enabled in `project-registry.yaml`; semantic retrieval remains disabled until a
real need justifies embeddings, stores, and ingestion implementations. A
completed run never triggers an extra model call merely to create memory.

## Adding an agent or workflow

Create an agent with two files:

```text
agent-config/agents/<agent-id>/
├── agent.yaml
└── instructions.md
```

Declare its workflow, skills, permitted tools, and optional model profile in `agent.yaml`. The registry discovers it automatically and rejects missing fields, unknown references, duplicate IDs, and paths that escape configured roots.

Add reusable step definitions to
`agent-runtime/agent-monorepo/workflows/workflow-steps.yaml`, then compose
them by `ref` in the adjacent `workflow-orchestrator.yaml`. The supported
primitives are `agent`, `tool`, `shell`, `hook`, and `parallel`, with named
`when`, `retry`, `timeout`, and `depends_on` controls. Keep web research in the
planning workflow so execution remains bounded to the approved plan.

## Verification

Run the complete offline suite and import checks with:

```bash
.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-gateway agent-tools/internal-messaging agent-tools/ui-debugger agent-config/agents/agent-implementation-planner agent-config/agents/agent-logs-analyzer
.venv/bin/python -m pytest -q
```

The tests inject fake Codex transports, so normal verification does not need network access or a model turn. They cover routing, workflow dependencies and concurrency, event durability, finalization, protocol normalization, approvals, resume, failure, and cancellation. A bounded live smoke check can validate the App Server initialize handshake without starting a model turn.

## Source-of-truth order

When sources disagree, follow this order:

```text
user instruction
  → current repository code, configuration, and tests
  → agent.yaml and workflow YAML
  → maintained architecture or ADR
  → durable project memory
  → runtime session history
```

Runtime logs are evidence of what happened. They are never application configuration.
