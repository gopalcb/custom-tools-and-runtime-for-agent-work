# Agent Platform Architecture

## 1. Architectural intent

This monorepo uses a **single agent platform boundary** under `agents/`. The goal is to support many dedicated project agents while keeping creation, loading, execution, memory, skills, and observation consistent.

The platform follows four design rules:

1. **One stable gateway** for agent lifecycle mechanics.
2. **Configuration-first agents** rather than unique runtime implementations per agent.
3. **Project resolution before context loading** so unrelated agents do not consume context.
4. **Progressive complexity**: V1.0 is local/simple; semantic routing, memory, observation, and durable workflows plug in later.

---

## 2. Top-level structure

```
monorepo/
├── AGENT_MAP.md
├── project-registry.yaml
├── IMPLEMENTATION.md
├── ARCHITECTURE.md
└── agents/
    ├── agent-runtime/
    ├── agent-gateway/
    ├── agent-builder/
    ├── agent-ui-builder/
    ├── skills/
    ├── memory/
    ├── evaluations/
    └── .agent-state/
```

---

## 3. Root files

### `AGENT_MAP.md`

**Audience:** Codex/Claude/humans.

Purpose:
- concise map of available agents and common infrastructure
- explain routing and naming rules
- allow a newly started coding agent to understand the agent platform quickly

It is **not** the machine source of truth for routing metadata.

### `project-registry.yaml`

**Audience:** Python resolver.

Purpose:
- register project/agent identifiers
- record agent paths
- provide aliases and semantic descriptions
- later become the corpus used by local semantic project selection

V1.0 agents are `agent-builder` and `agent-ui-builder`.

### `IMPLEMENTATION.md`

**Audience:** Claude Code/Codex/engineers implementing the roadmap.

Purpose:
- current implementation status
- setup/run commands
- invariants that must not be broken
- next implementation phases
- known deferred functionality

### `ARCHITECTURE.md`

**Audience:** engineers and agent maintainers.

Purpose:
- define boundaries and ownership
- explain every directory and important file
- prevent responsibilities from drifting between components

---

# 4. `agents/agent-runtime/`

Runtime selection/orchestration infrastructure that sits **before** an individual agent is loaded.

It answers:

> Which one project/agent should receive this request?

It does not decide how Codex threads run and does not materialize agent files.

## `agent-runtime/agent-monorepo/`

Monorepo-wide resolver.

### `bootstrap.py`

Entry/bootstrap utility.

Responsibilities:
- find monorepo root
- load `project-registry.yaml`
- ask resolver to choose a project
- return normalized project/agent/path metadata
- guarantee resolved path remains inside monorepo

It currently does **not** start Codex itself. Keeping resolution independent from execution makes it testable and lets the caller decide whether to load/run/resume the selected agent.

### `resolver.py`

V1.0 deterministic project resolver.

Responsibilities:
- explicit project detection
- alias detection
- active-project continuity
- lexical fallback

Later semantic matching should be added without changing the public concept: return exactly one project.

### `semantic_search.py`

Intentionally blank in V1.0.

Future responsibility:
- local embedding model initialization
- project description embedding/cache
- prompt embedding
- cosine similarity retrieval

It must search project registry metadata, not the whole source repository.

---

# 5. `agents/agent-gateway/`

The central reusable agent control-plane package.

It answers:

> Given a known agent, how do we build/load/execute it consistently?

No generated project agent should duplicate this behavior.

## `pyproject.toml`

Defines the installable `monorepo-agent-gateway` Python package.

Core dependencies:
- Pydantic — strict runtime/config models
- PyYAML — machine configuration
- Jinja2 — safe standardized scaffold rendering

Optional dependency:
- `openai-codex` — runtime provider

## `README.md`

Short package-level orientation.

## `src/agent_gateway/__init__.py`

Small public import surface.

Exports the gateway and key models.

## `gateway.py`

**Facade / public API.**

Responsibilities:
- list agents
- load an agent
- validate an agent
- build a new scaffold from an already-designed spec
- run a new session
- resume an existing session

Callers should prefer this class over directly importing provider/registry/builder internals.

## `models.py`

Shared Pydantic contracts.

Key models:
- `RuntimeConfig`
- `PermissionConfig`
- `AgentSpec`
- `LoadedAgent`
- `AgentRunResult`

Purpose:
- prevent arbitrary dict/string contracts between modules
- provide one validated representation of machine configuration

## `registry.py`

Filesystem-backed registry view.

Responsibilities:
- derive direct child path for an agent id
- list valid configured agents
- check existence
- parse `agent.yaml`

It excludes infrastructure directories such as `agent-gateway`, `agent-runtime`, `skills`, and state directories from the agent list.

## `builder.py`

Filesystem materializer.

Responsibilities:
- receive a validated `AgentSpec` + template context
- render standard templates into a temporary directory
- validate rendered `agent.yaml`
- write a direct child under `agents/`
- protect existing agents by default

Important boundary:

`builder.py` does not decide purpose, responsibilities, or workflows. That belongs to `agent-builder/designer.py`.

## `loader.py`

Loads one agent into a `LoadedAgent` object.

Reads:
- `agent.yaml`
- `AGENT.md`
- `skills.yaml`
- `evals.yaml`

Later this is the natural integration point for project context and memory assembly.

## `runtime.py`

Runtime provider selector.

Responsibilities:
- choose provider from `agent.yaml`
- resolve and validate configured working directory
- call provider `run_new` or `resume`

It keeps provider-specific code out of the gateway facade.

---

## `providers/`

Provider adapter layer.

### `base.py`

Abstract provider contract:
- `run_new(...)`
- `resume(...)`

### `codex.py`

V1.0 production runtime adapter.

Uses the official `openai-codex` Python SDK through lazy import.

Current SDK architecture represented by this adapter:

```
Codex client
  -> thread_start / thread_resume
  -> Thread.run
  -> TurnResult
```

Sandbox configuration maps agent config values to official sandbox presets.

Only this adapter should need changes if Codex SDK details change.

Official references verified while creating this scaffold:
- https://github.com/openai/codex/blob/main/sdk/python/docs/getting-started.md
- https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md
- https://github.com/openai/codex/blob/main/sdk/python/docs/faq.md

### `openai_agents.py`

Placeholder provider.

Purpose:
- preserve provider independence
- allow future OpenAI Agents SDK runtime without changing `agent.yaml` architecture or gateway callers

It intentionally raises `NotImplementedError` in V1.0.

---

## `context/`

Future context assembly boundary.

### `loader.py`

Currently provides a minimal optional `PROJECT_CONTEXT.md` loader.

Future responsibility:
- project map/context
- architecture decisions
- relevant repository metadata

### `assembler.py`

Combines already-selected context parts.

This should remain a formatting/assembly component, not a retrieval engine.

---

## `skills/`

Skill-resolution boundary.

### `resolver.py`

V1.0 resolves a unique skill directory by skill id.

Future responsibility:
- validate required skill references
- retrieve only relevant skills
- apply common vs task-specific skill loading policy

---

## `memory/`

Memory provider boundary.

### `provider.py`

Defines `MemoryProvider` protocol and `NoOpMemoryProvider`.

V1.0 deliberately retrieves nothing.

Future implementations can use SQLite/sqlite-vec, pgvector, Qdrant, or another backend without changing agent definitions.

---

## `lifecycle/`

Lifecycle hook boundary.

### `hooks.py`

Defines extension points:
- `before_run`
- `after_run`
- `on_failure`

Future Observer Agent and remote logging should attach here instead of being hard-coded into every provider.

---

## `observability/`

Tracing boundary.

### `tracing.py`

Minimal local span shim.

Future target:
- OpenTelemetry trace/span adapter
- run/session/agent attributes
- tool calls
- memory retrieval spans
- observer/evaluation spans

---

# 6. `agents/agent-builder/`

This is the primary V1.0 agent/project.

It answers:

> What should a newly requested agent look like?

It is not the runtime framework.

## Root agent artifacts

### `agent.yaml`

Machine-readable runtime configuration for the Agent Builder itself.

Defines:
- id/version
- purpose/description
- instruction/skill/eval filenames
- runtime provider
- sandbox/workspace
- permissions

### `AGENT.md`

Behavioral instructions for the Agent Builder.

Defines:
- mission
- architecture invariants
- build workflow
- quality expectations

### `skills.yaml`

References reusable skills required by the builder.

### `evals.yaml`

Initial evaluation contract for the builder.

This is intentionally present before the observer/evaluation engine exists.

## `pyproject.toml`

Installable Agent Builder service package.

Dependencies include Pydantic, YAML/Jinja rendering support, FastAPI, and Uvicorn.

## `README.md`

Agent-local orientation.

---

## `src/agent_builder/`

### `models.py`

Builder-specific Pydantic contracts:
- `AgentBuildRequest`
- `AgentDesign`
- `AgentBuildResult`

These models are separate from gateway runtime models because a design request contains higher-level intent that is not runtime configuration.

### `designer.py`

V1.0 deterministic design engine.

Responsibilities:
- normalize agent id once
- infer safe baseline responsibilities when not supplied
- create common workflow steps
- add mandatory foundational skills
- preserve explicit restrictions
- create initial evaluation requirements

Future Codex/LLM enhancement should refine the structured `AgentDesign`, not write files directly.

### `validator.py`

Validates a design before materialization.

Responsibilities:
- reject reserved names
- require meaningful purpose
- require responsibilities/workflow/evals
- ensure direct-child destination under `agents/`
- protect existing destinations unless overwrite is explicit

### `service.py`

Application orchestration layer.

`preview()`:
- design
- validate structure
- no writes

`build()`:
- design
- validate
- convert to Gateway `AgentSpec`
- call `AgentGateway.build`
- reload/validate generated agent
- return paths/result

### `api.py`

FastAPI transport adapter.

Endpoints:
- `/health`
- `/v1/agents`
- `/v1/agents/preview`
- `/v1/agents/build`

Business logic must remain in `service.py`, not accumulate in HTTP handlers.

---

## `templates/`

Standard output contract for generated agents.

### `agent.yaml.j2`

Machine configuration template.

### `AGENT.md.j2`

Behavioral instruction template.

### `skills.yaml.j2`

Skill reference template.

### `evals.yaml.j2`

Initial evaluation template.

Agent Builder may improve content passed to these templates, but generated agents should preserve this standard four-file contract unless architecture is deliberately revised.

---

# 7. `agents/agent-ui-builder/`

V1.0 UI-focused agent/project.

It answers:

> How should the user interact with an agent workflow?

## `agent.yaml`, `AGENT.md`, `skills.yaml`, `evals.yaml`

Same standard agent contract as Agent Builder, with UI-specific responsibility and scope.

## `README.md`

Explains V1.0 UI artifact.

## `ui/index.html`

Zero-build standalone HTML mockup.

Responsibilities:
- capture name/purpose/context/workflow/skills/restrictions
- locally preview request JSON
- optionally POST build requests to Agent Builder API
- display success/error without losing input state

Why plain HTML for V1.0:
- fastest iteration
- no frontend build chain
- easy to replace later after workflow stabilizes
- keeps focus on Agent Builder architecture rather than UI framework work

---

# 8. `agents/skills/`

Shared reusable behavioral/procedural capabilities.

Current structure:

```
skills/
├── common/
│   ├── repository-navigation/
│   └── safe-file-editing/
└── agent-development/
    ├── agent-design/
    ├── agent-validation/
    └── prompt-design/
```

Each skill is a separate `SKILL.md` so agents reference capabilities instead of copying instructions.

Future domains such as Angular/AWS should be added only when those agents are introduced.

---

# 9. `agents/memory/`

Reserved persistent memory domain.

```
memory/
├── agents/
│   ├── agent-builder/
│   └── agent-ui-builder/
└── semantic/
```

### `memory/agents/<agent-id>/`

Future agent-specific memory records.

### `memory/semantic/`

Future embedding index/storage.

No memory backend is implemented in .0.

---

# 10. `agents/evaluations/`

Reserved evaluation evidence/data domain.

### `runs/`

Future per-run observer/evaluation outputs.

### `datasets/`

Future regression cases and benchmark tasks.

Per-agent `evals.yaml` defines expectations; this directory stores shared execution evidence/datasets later.

---

# 11. `agents/.agent-state/`

Local ephemeral/runtime state. This should normally be ignored by source control except `.gitkeep` placeholders.

### `sessions/`

Future local mapping between user/agent tasks and runtime thread ids.

### `cache/`

Future project embeddings, registry cache, derived indexes.

### `logs/`

Future runtime/control-plane logs.

Do not store secrets here merely because it is hidden by a dot prefix.

---

# 12. Request lifecycle

## V1.0 resolution + load

```
User prompt
   |
   v
agent-runtime/agent-monorepo
   |
   v
project-registry.yaml
   |
   v
one project / one agent
   |
   v
AgentGateway.load(agent_id)
   |
   +--> agent.yaml
   +--> AGENT.md
   +--> skills.yaml
   +--> evals.yaml
```

## V1.0 agent creation

```
UI / API / coding agent
        |
        v
AgentBuildRequest
        |
        v
AgentDesigner
        |
        v
AgentDesignValidator
        |
        v
AgentSpec
        |
        v
AgentGateway.build
        |
        v
AgentFilesystemBuilder
        |
        v
agents/agent-<name>/
```

## Future learning lifecycle

```
AgentGateway.run
      |
      v
runtime provider
      |
      v
actual task outcome
      |
      v
lifecycle.after_run
      |
      v
observer + deterministic evidence
      |
      v
episodic/semantic/procedural memory
      |
      v
improvement proposal
      |
      v
regression gate + version bump
```

---

# 13. Trust boundaries

## Filesystem

Gateway builder restricts generated agents to direct children of `agents/`.

Runtime `workspace` is resolved against monorepo root and checked against traversal outside the root.

This is an application-level boundary in addition to Codex sandbox behavior; it is not a replacement for OS/process isolation in a hosted multi-user system.

## Configuration

`agent.yaml` is validated through Pydantic before becoming runtime configuration.

## Templates

Jinja uses `StrictUndefined` so missing required context fails instead of silently rendering incomplete files.

## Existing agents

Overwrite defaults to false.

---

# 14. Extension principles

When adding functionality, prefer these extension points:

| Need | Extend |
|---|---|
| Better project selection | `agent-runtime/agent-monorepo/semantic_search.py` |
| New runtime provider | `agent-gateway/providers/` |
| More context sources | `agent-gateway/context/` |
| Skill loading/validation | `agent-gateway/skills/` |
| Persistent memory | `agent-gateway/memory/` |
| Observer hooks | `agent-gateway/lifecycle/` |
| Distributed tracing | `agent-gateway/observability/` |
| Better generated agent reasoning | `agent-builder/designer.py` or a new design enhancer |
| UI framework | replace/extend `agent-ui-builder/ui/` after workflow stabilizes |

Do not solve a shared problem by adding private implementation to one generated agent.
