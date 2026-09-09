# Agent Builder (/agents/agent-builder) V1.0 — Implementation Guide (Initial implementation complete)

**Audience:** Claude Code / Codex / engineers continuing implementation.

**Status:** V1 scaffold is implemented. The local semantic resolver, observer agent, persistent memory, and full evaluation runner are intentionally deferred.

## 1. Goal

Build a production-oriented foundation for creating and running monorepo agents without creating a custom agent framework for every agent. Generated agents become discoverable by the filesystem-backed Agent Gateway registry; adding a generated agent to the monorepo project resolver (`project-registry.yaml`) is a separate mapping step in V1.

The system has four responsibilities:

1. **Monorepo resolver** — decide which one project/agent should handle a request.
2. **Agent Gateway** — common build/load/run/resume infrastructure.
3. **Agent Builder** — convert a concise agent request into a validated agent design and scaffold.
4. **Agent UI Builder** — V1 standalone HTML interface for submitting/previewing build requests.

The V1 architecture deliberately does **not** implement scoring, multi-agent routing, semantic memory, observer-driven self-modification, or durable workflow orchestration.

---

## 2. Non-negotiable conventions

Claude Code should preserve these unless the user explicitly changes the architecture.

### 2.1 Agent platform boundary

All agent-specific or agent-platform artifacts belong under - `agents/`

Root-level exceptions are only:

```
AGENT_MAP.md
project-registry.yaml
IMPLEMENTATION.md
ARCHITECTURE.md
```

### 2.2 Agent naming

New agents are normalized exactly once:

```
aws-deployment -> agent-aws-deployment 
agent-aws-deployment -> agent-aws-deployment
```

Never generate:

```
agent-agent-aws-deployment
```

`agents/agent-builder` and `agents/agent-ui-builder` are already both the project home and agent home; there is no duplicate `projects/` hierarchy.

### 2.3 Separation of concerns

- `agent-builder` decides **what an agent should be**.
- `agent-gateway` decides **how agent artifacts are built, loaded, and executed**.
- `agent-runtime/agent-monorepo` decides **which project/agent is active**.
- generated agents contain configuration/instructions/skill references/evals, not duplicated gateway/runtime code.

### 2.4 Safe writes

Agent creation must:

- stay under `agents/`
- create a direct child only (`agents/agent-*`)
- validate generated `agent.yaml` before repository write
- refuse overwrite by default
- avoid recursive deletion in V1

---

## 3. Current implementation state

### Implemented

- project registry and human-readable agent map
- deterministic V1 project resolver
- monorepo root discovery
- gateway registry, models, loader, builder, runtime facade
- Codex provider adapter using the official Python SDK surface
- OpenAI Agents provider placeholder
- context/skill/memory/lifecycle/observability extension points
- deterministic V1 Agent Designer
- design validation
- Jinja templates for new agents
- FastAPI preview/build endpoints
- self-contained Agent Builder HTML mockup
- initial reusable agent-development skills
- empty state/memory/evaluation directories

### Intentionally deferred

- `semantic_search.py` implementation
- embeddings/vector index
- observer agent
- long-term/episodic/semantic memory
- automated agent improvement/promotion
- evaluation runner and regression gates
- multi-agent orchestration
- LangGraph/Temporal/durable workflow runtime
- OpenAI Agents provider
- authentication/authorization for the local API
- production deployment of Agent Builder API

---

## 4. Environment setup

From the existing monorepo root:

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e agents/agent-gateway
pip install -e agents/agent-builder
```

To use the Codex provider as well:

```
pip install -e 'agents/agent-gateway[codex]'
```

The official Codex Python SDK package is `openai-codex`. Current official documentation states Python >=3.10 and provides `Codex.thread_start(...)`, `thread_resume(...)`, `Thread.run(...)`, sandbox presets, and existing Codex authentication reuse.

Reference:
- https://github.com/openai/codex/blob/main/sdk/python/docs/getting-started.md
- https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md

---

## 5. Run the resolver

From the monorepo root:

```
python agents/agent-runtime/agent-monorepo/bootstrap.py "create an agent for AWS deployments"
```

Expected shape:

```
{
  "project": "agent-builder",
  "agent_id": "agent-builder",
  "agent_path": ".../agents/agent-builder",
  "reason": "..."
}
```

V1 resolver order:

1. explicit project name
2. configured alias
3. active project
4. lexical overlap

Do not make this resolver LLM-based. `semantic_search.py` will later replace lexical fallback with local embeddings.

---

## 6. Run the Agent Builder API

From the monorepo root with the venv active:

```
uvicorn agent_builder.api:app --app-dir agents/agent-builder/src --reload --port 8000
```

Optional if starting from another directory:

```
export MONOREPO_ROOT=/absolute/path/to/monorepo
```

Endpoints:

```
GET  /health
GET  /v1/agents
POST /v1/agents/preview
POST /v1/agents/build
```

### Preview example

```
curl -X POST http://127.0.0.1:8000/v1/agents/preview \
  -H 'content-type: application/json' \
  -d '{
    "name": "aws-deployment",
    "purpose": "Deploy and maintain AWS infrastructure safely with CDK.",
    "context": "The project uses CDK, Lambda, API Gateway and DynamoDB.",
    "required_skills": ["aws-cdk", "iam-validation"],
    "restrictions": ["Validate AWS identity before deployment."]
  }'
```

Preview returns `AgentDesign` and never writes files.

### Build example

Use the same payload with:

```
POST /v1/agents/build
```

Expected output directory:

```
agents/agent-aws-deployment/
├── agent.yaml
├── AGENT.md
├── skills.yaml
└── evals.yaml
```

By default, a duplicate destination returns HTTP 409.

---

## 7. Open the UI mockup

Open directly in a browser:

```
agents/agent-ui-builder/ui/index.html
```

`Preview` is fully local and simply renders the request JSON.

`Build Agent` calls:

```
http://127.0.0.1:8000/v1/agents/build
```

Serve the UI with a tiny local server so it uses one of the V1 API's explicitly allowed development origins:

```
cd agents/agent-ui-builder/ui
python -m http.server 8080
```

Then visit:

```
http://127.0.0.1:8080
```

The API currently allows only `http://127.0.0.1:8080` and `http://localhost:8080` for this local mockup. Replace these with trusted deployment origins in any hosted environment; do not switch to wildcard production CORS.

---

## 8. How Agent Builder works

```
AgentBuildRequest
      |
      v
AgentDesigner
      |
      v
AgentDesign (Pydantic)
      |
      v
AgentDesignValidator
      |
      v
AgentSpec (Gateway Pydantic model)
      |
      v
AgentGateway.build()
      |
      v
AgentFilesystemBuilder
      |
      +--> render templates in a temporary directory
      +--> validate rendered agent.yaml
      +--> create agents/agent-<name>/
      |
      v
AgentGateway.validate()
```

### Why this split matters

The LLM/agent design layer must never have arbitrary direct control over filesystem layout. Even when a Codex design enhancer is added later, it should return structured `AgentDesign`; the validator and gateway keep control of writes.

---

## 9. V1 Agent Designer

`agents/agent-builder/src/agent_builder/designer.py` is intentionally deterministic.

It:

- normalizes the agent id
- fills baseline responsibilities when missing
- creates a standard execution workflow
- adds mandatory repository/safe-editing skills
- preserves caller-provided skills/restrictions
- generates initial evaluation requirements

This makes the builder useful before adding nested model calls.

### Recommended next enhancement

Add a **CodexDesignEnhancer**, but keep the flow:

```
request -> deterministic draft -> Codex structured refinement -> Pydantic validation -> gateway write
```

Do not let Codex write the generated agent directory directly during the design phase.

The enhancer should be optional so local deterministic builds remain available.

---

## 10. Gateway contract

Use `AgentGateway` from agent projects rather than importing provider classes.

```
from agent_gateway import AgentGateway

gateway = AgentGateway(monorepo_root)
agent = gateway.load("agent-builder")
result = gateway.run("agent-builder", "Create an agent for ...")
```

Public V1 methods:

```
list_agents()
load(agent_id)
validate(agent_id)
build(spec, template_dir, template_context, overwrite=False)
run(agent_id, prompt)
resume(agent_id, session_id, prompt)
```

Do not add project-specific methods to `AgentGateway`.

---

## 11. Codex provider

The provider is in:

```
agents/agent-gateway/src/agent_gateway/providers/codex.py
```

V1 uses the official SDK model:

```
with Codex() as codex:
    thread = codex.thread_start(...)
    result = thread.run(prompt)
```

and for continuity:

```
thread = codex.thread_resume(session_id, ...)
```

The provider intentionally imports `openai_codex` lazily so non-runtime operations do not require the optional package.

### Important SDK assumptions verified for this scaffold

As of 2026-09-09, official Codex Python SDK documentation exposes:

- package: `openai-codex`
- import: `from openai_codex import Codex, Sandbox`
- `thread_start(...)`
- `thread_resume(thread_id, ...)`
- `Thread.run(...)`
- `Sandbox.read_only`
- `Sandbox.workspace_write`
- `Sandbox.full_access`

If SDK APIs change later, update only the provider adapter; do not change agent definitions.

---

## 12. Generated `agent.yaml`

Machine-readable configuration is authoritative for runtime loading.

Core fields:

```
id: agent-example
version: 0.1.0
description: ...
purpose: ...
instructions_file: AGENT.md
skills_file: skills.yaml
evals_file: evals.yaml
runtime:
  provider: codex
  sandbox: workspace-write
  workspace: agents
permissions:
  filesystem_read: ["."]
  filesystem_write: ["."]
  shell: true
  network: controlled
```

Do not hide runtime or permission policy only in prose.

---

## 13. Skills

Reusable skills live under:

```
agents/skills/<category>/<skill-id>/SKILL.md
```

V1 includes:

```
repository-navigation
safe-file-editing
agent-design
agent-validation
prompt-design
```

Generated `skills.yaml` stores identifiers, not copied skill bodies.

The gateway skill resolver is intentionally basic and should evolve with the memory/context loader rather than becoming agent-specific.

---

## 14. Semantic project resolution — next phase

`agents/agent-runtime/agent-monorepo/semantic_search.py` is intentionally blank.

Recommended implementation:

1. Treat `project-registry.yaml` descriptions and aliases as the small routing corpus.
2. Embed that corpus locally once and cache vectors under `agents/.agent-state/cache/`.
3. Embed each new user prompt locally.
4. Use cosine similarity to select one project.
5. Keep the project->agent relationship deterministic.
6. Preserve active project for short follow-up prompts such as "now add tests".
7. Do not vector-search the whole codebase to decide project ownership.

For a small number of projects, an in-process sentence-transformer and NumPy cosine similarity is sufficient. Do not add Qdrant/FAISS solely for routing.

---

## 15. Memory — later phase

The directory exists, but V1 uses `NoOpMemoryProvider`.

Future memory must remain behind the gateway provider contract. Recommended layers:

```
working memory       current task only
short-term memory    recent tasks/session
episodic memory      what happened in previous tasks
semantic memory      distilled facts/rules + embeddings
procedural memory    reusable skills/workflows
failure memory       known anti-patterns and failed approaches
architecture memory  project decisions/ADRs
```

Do not make every agent implement its own vector store.

---

## 16. Observer/evaluation — later phase

Each agent includes `evals.yaml` now so evaluation criteria exist before an observer is implemented.

Future lifecycle:

```
run
 -> deterministic evidence (tests/build/diff)
 -> observer evaluation
 -> episode/reflection
 -> memory consolidation
 -> improvement proposal
 -> regression validation
 -> version bump
```

Do **not** allow an observer to silently rewrite `AGENT.md` after every task.

---

## 17. Production hardening backlog

Recommended order:

### Phase 1 — complete local V1

- add unit/integration tests
- add CORS dev configuration only if UI/API are served separately
- validate referenced skills exist
- make generated agent registry update atomic if registry starts tracking generated agents
- add structured error codes to API
- add safe atomic directory replacement for explicit overwrite

### Phase 2 — semantic routing

- implement local embedding model
- cache project embeddings
- active-project session state
- deterministic fallback when similarity is weak

### Phase 3 — runtime lifecycle

- lifecycle hooks wired into gateway
- structured run records under `.agent-state/sessions`
- OpenTelemetry tracing adapter
- tool/file-change metadata capture

### Phase 4 — observer + memory

- observer agent
- episodic storage
- semantic memory index
- consolidation and forgetting policies
- confidence/evidence tracking

### Phase 5 — improvement gates

- versioned improvement proposals
- regression datasets
- human approval for instruction/skill changes initially
- rollback when new version underperforms

---

## 18. What Claude Code should NOT do without explicit instruction

- Do not reintroduce root `/projects` or root `/packages` for this platform.
- Do not create `agents/agent-agent-builder`.
- Do not replace the gateway facade with direct Codex calls scattered across agents.
- Do not implement semantic search by scanning/embedding the entire monorepo.
- Do not add LangGraph, Qdrant, Redis, Postgres, Temporal, or cloud infrastructure merely because they may be useful later.
- Do not make agent self-modification automatic in V1.
- Do not put secrets/tokens into agent YAML, logs, memory, or source control.
- Do not give generated agents unrestricted filesystem/network permissions by default.

---

## 19. First tasks for Claude Code after importing this scaffold

1. Install both editable Python packages and run import checks.
2. Start the FastAPI service and call `/health`.
3. Call `/v1/agents/preview` with a sample request.
4. Build a disposable sample agent such as `agent-test-builder-output`.
5. Inspect the four generated files.
6. Confirm a duplicate build is rejected.
7. Remove the disposable agent manually after verification.
8. Add tests only when the user asks to begin the testing phase.

This sequence validates architecture wiring before adding intelligence.
