# Refined Agent Monorepo Architecture, Workflow Orchestration & Codex Console Specification

**Status:** Proposed refined architecture  
**Supersession note:** The root `agent-console/` Flask project and
`monorepo-agentic-dev` entry point have been removed. The browser control
surface now lives under `agent-runtime/monorepo-controller/`; the Python runtime
keeps the thin gateway and shared execution object graph.
**Primary goal:** Keep the agent platform compact, readable, reusable, and easy to evolve without creating a large number of thin Python/TypeScript files.  
**Design reference:** `codex-agent-console-ui-mockup.html`  
**Implementation style:** Python-first control plane, declarative YAML/Markdown agent definitions, minimal runtime modules, event-driven TUI, deferred semantic-memory infrastructure.

---

## 1. Executive Summary

The current direction is strong, but the proposed structure has too many files that represent concepts rather than meaningful implementation boundaries.

The main duplication is between:

- `agent-gateway/`
- `agent-runtime/agent-monorepo/`
- runtime logging modules
- runtime memory modules
- the planned `agent-memory-sdk`

Several current files can be merged because they would otherwise contain only one small class, type, policy, or forwarding function.

The refined architecture should follow these rules:

1. **Keep the gateway thin.**
   - The gateway is a stable entry point.
   - It should not own execution, lifecycle, context, skills, provider logic, or memory.

2. **Keep one runtime.**
   - Resolution, workflow execution, Codex integration, logging, post-completion processing, and runtime memory access belong to the runtime.

3. **Make agents declarative by default.**
   - An agent directory should mostly contain:
     - `agent.yaml`
     - `instructions.md`
   - Do not create Python classes per agent unless the agent truly requires custom deterministic logic.

4. **Use one workflow engine, not one Python workflow class per workflow.**
   - Workflows are YAML.
   - A small `workflow.py` executes them.

5. **Use one event model everywhere.**
   - Runtime instrumentation
   - JSONL logging
   - metrics
   - post-completion
   - terminal UI
   - background task state

   should all consume the same `RuntimeEvent`.

6. **Log facts continuously.**
   - The runtime writes authoritative events immediately.
   - A post-completion hook reads the completed event stream and derives summaries/metrics/artifacts.

7. **Do not create empty provider/store Python classes just to reserve architecture.**
   - Keep future directories.
   - Use `README.md` or `.gitkeep` until there is real implementation.

8. **Use Python for the runtime and custom terminal UI.**
   - It avoids a Python↔Node bridge.
   - It allows the TUI to directly consume the runtime event stream.

9. **Use Codex App Server as the Codex integration boundary.**
   - Do not scrape or parse the visible Codex terminal UI.
   - Treat Codex as an agent harness exposed through a structured protocol.

10. **Do not build a general-purpose workflow platform yet.**
    - Start with ordered steps.
    - Add conditional steps.
    - Add small parallel groups.
    - Add retry.
    - Avoid implementing a full DAG engine, Temporal-like scheduler, or distributed execution system prematurely.

---

# 2. Recommended Final Structure

```text
monorepo/
│
├── AGENTS.md
├── project-registry.yaml
├── pyproject.toml
│
├── agents/
│   │
│   ├── agent-builder/
│   │   ├── agent.yaml
│   │   └── instructions.md
│   │
│   ├── agent-ui-builder/
│   │   ├── agent.yaml
│   │   └── instructions.md
│   │
│   ├── planner-agent/
│   │   ├── agent.yaml
│   │   └── instructions.md
│   │
│   └── ...
│
├── workflows/
│   └── workflow-orchestrator.yaml
│
├── agent-gateway/
│   └── gateway.py
│
├── agent-runtime/
│   └── agent-monorepo/
│       ├── __init__.py
│       ├── bootstrap.py
│       ├── registry.py
│       ├── resolver.py
│       ├── runtime.py
│       ├── workflow.py
│       ├── events.py
│       ├── post_completion.py
│       │
│       └── memory/
│           ├── service.py
│           ├── retrieval.py
│           │
│           ├── ingestion/
│           │   └── .gitkeep
│           │
│           ├── embeddings/
│           │   └── README.md
│           │
│           └── stores/
│               └── README.md
│
├── agent-console/
│   ├── console.py
│   └── console.tcss
│
├── .agent-state/
│   ├── cache/
│   │   └── .gitkeep
│   ├── logs/
│   │   └── .gitkeep
│   └── sessions/
│       └── .gitkeep
│
└── docs/
    └── mockups/
        └── codex-agent-console-ui-mockup.html
```

This is intentionally small.

The initial production control plane is approximately:

```text
1 gateway file
7 core runtime files
2 memory files
2 console files
1 workflow YAML
2 files per agent
```

That is enough to support the current architecture without introducing dozens of abstractions.

---

# 3. Files to Remove or Merge

## 3.1 `agent-gateway/`

Current proposal:

```text
agent-gateway/
├── gateway.py
├── models.py
├── registry.py
├── loader.py
├── runtime.py
├── lifecycle.py
├── memory.py
├── skills.py
├── context.py
└── providers.py
```

Recommended:

```text
agent-gateway/
└── gateway.py
```

### Why

The gateway should only be a facade.

It receives a request and delegates it to the runtime.

It should not duplicate runtime concerns.

Conceptually:

```python
class AgentGateway:
    async def run(self, request: RunRequest):
        async for event in self.runtime.run(request):
            yield event
```

The gateway can later be wrapped by:

- CLI/TUI
- Flask/FastAPI
- desktop application
- Angular local development bridge
- remote service

without changing the runtime.

### Remove from gateway

| Current file | Action | New owner |
|---|---|---|
| `models.py` | remove | shared runtime types kept close to implementation |
| `registry.py` | move/merge | `agent-runtime/.../registry.py` |
| `loader.py` | merge | `registry.py` |
| `runtime.py` | remove | core runtime `runtime.py` |
| `lifecycle.py` | merge | `runtime.py` + events |
| `memory.py` | remove | `memory/service.py` |
| `skills.py` | merge | resolver/registry reads skill references |
| `context.py` | merge | resolver/runtime builds run context |
| `providers.py` | remove initially | Codex adapter stays in `runtime.py` until it becomes large |

---

# 4. Runtime File Responsibilities

## 4.1 `bootstrap.py`

Purpose:

> Build the application object graph once.

Responsibilities:

- locate repository root;
- load `project-registry.yaml`;
- initialize registry;
- initialize event infrastructure;
- initialize memory service;
- initialize resolver;
- initialize workflow engine;
- initialize Codex runtime client;
- construct `AgentRuntime`;
- construct `AgentGateway`.

Avoid business logic here.

Example conceptual API:

```python
def bootstrap(project_root: Path) -> AgentGateway:
    ...
```

No global singletons are required.

---

## 4.2 `registry.py`

This replaces both `registry.py` and `loader.py`.

Purpose:

> Load and cache declarative project definitions.

Responsibilities:

- read `project-registry.yaml`;
- discover `agents/*/agent.yaml`;
- load `instructions.md`;
- load workflow definitions;
- resolve configured skill paths;
- validate required fields;
- cache parsed configuration.

Suggested objects:

```python
@dataclass(frozen=True)
class AgentDefinition:
    id: str
    instructions_path: Path
    workflow: str
    skills: tuple[str, ...]
    model_profile: str | None
    tools: tuple[str, ...]
```

```python
class Registry:
    def get_agent(self, agent_id: str) -> AgentDefinition: ...
    def get_workflow(self, workflow_id: str) -> dict: ...
    def list_agents(self) -> list[AgentDefinition]: ...
```

Do not create separate loaders for:

- agents;
- skills;
- workflows;
- project registry;

until their parsing logic becomes materially different.

---

## 4.3 `resolver.py`

Purpose:

> Convert a user request into a compact executable run specification.

The resolver should be mostly deterministic.

It decides:

- which agent to use;
- which workflow to use;
- which skills are relevant;
- whether planning is needed;
- whether external web search is needed;
- what local project context should be retrieved;
- what verification profile should apply.

Example result:

```python
@dataclass
class ResolvedRunSpec:
    agent_id: str
    workflow_id: str
    skills: list[str]
    tools: list[str]
    needs_planning: bool
    needs_web_search: bool
    context_queries: list[str]
    validation_commands: list[str]
```

### Important rule

Do **not** call a planner agent for every prompt.

Use deterministic resolution first.

Call `planner-agent` only when:

- task scope is non-trivial;
- implementation order is not obvious;
- multiple subsystems are involved;
- the selected workflow explicitly requires a planning step.

This reduces unnecessary model calls.

---

## 4.4 `runtime.py`

Purpose:

> Own one agent run.

This is the main execution service.

Responsibilities:

- create run/session identifiers;
- create `RunContext`;
- communicate with Codex;
- execute agent turns;
- dispatch tool calls;
- coordinate workflow execution;
- publish runtime events;
- maintain cancellation state;
- maintain child/background task handles;
- close/finalize a run.

### Codex integration

For the custom console, use the Codex App Server as the preferred long-lived integration boundary.

Conceptually:

```text
Python runtime
     │
     ├── launch: codex app-server
     │
     ├── stdin  → JSONL request messages
     └── stdout ← JSONL response/notification messages
```

Keep the first implementation in `runtime.py`.

If the Codex protocol adapter grows beyond roughly 200–300 meaningful lines, extract:

```text
codex_client.py
```

Do not create this file before it is needed.

### Do not parse human CLI output

Bad:

```text
spawn `codex`
→ scrape colors/text
→ infer current step
```

Good:

```text
Codex structured protocol
→ normalize events
→ RuntimeEvent
→ UI/logging/workflow
```

---

## 4.5 `workflow.py`

Purpose:

> Execute declarative workflows.

Do not build one Python class per workflow.

Support only the capabilities required now:

- ordered steps;
- named conditions;
- agent step;
- tool step;
- shell/validation step;
- hook step;
- retry;
- small parallel groups;
- dependencies within one run.

Avoid implementing:

- arbitrary expression language;
- distributed scheduler;
- persistent workflow workers;
- cron;
- cross-machine queues;
- a general Temporal/Airflow replacement.

Example API:

```python
class WorkflowEngine:
    async def execute(
        self,
        definition: dict,
        context: RunContext,
    ) -> None:
        ...
```

A small handler map is enough:

```python
STEP_HANDLERS = {
    "agent": run_agent_step,
    "tool": run_tool_step,
    "shell": run_shell_step,
    "hook": run_hook_step,
}
```

---

## 4.6 `events.py`

Merge:

```text
logging/event_logger.py
logging/event_store.py
logging/event_types.py
```

into:

```text
events.py
```

This is one of the most important simplifications.

Purpose:

> One event contract for runtime facts, persistence, UI updates, and finalization.

Recommended event type:

```python
@dataclass(frozen=True)
class RuntimeEvent:
    seq: int
    type: str
    ts: str
    run_id: str
    session_id: str
    agent_id: str | None = None
    step_id: str | None = None
    status: str | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
```

Recommended service:

```python
class EventHub:
    async def emit(self, event: RuntimeEvent) -> None:
        ...
```

`emit()` should do two things:

```text
event
 ├── append to events.jsonl
 └── publish to in-process subscribers
```

Therefore:

- logging does not need one event implementation;
- UI does not need another;
- metrics does not need another;
- background tasks do not need another.

### Critical design rule

The console should **not tail `events.jsonl`** to update itself.

The runtime already has the event in memory.

Publish it immediately to the console and persist the same event to disk.

---

## 4.7 `post_completion.py`

Keep this as one file.

Purpose:

> Derive higher-level run artifacts after execution finishes.

It should not collect raw events.

Raw events have already been written by the runtime.

Example:

```python
async def post_completion(run: RunContext) -> None:
    events = event_hub.load_run(run.run_id)

    write_run_metadata(events)
    write_summary(events)
    write_metrics(events)
    write_artifacts_index(events)

    memory_service.prepare_candidates(events)
```

Initial outputs:

```text
run-<id>/
├── run.json
├── events.jsonl
├── summary.md
├── artifacts.json
└── memory_candidates.json
```

`memory_candidates.json` may initially contain:

```json
{
  "status": "disabled",
  "candidates": []
}
```

This preserves the contract without prematurely implementing AI memory extraction.

---

# 5. Refined Logging Architecture

Use runtime instrumentation for authoritative logging.

```text
                    Agent Runtime
                         │
          ┌──────────────┼───────────────┐
          │              │               │
     model events     tool events    workflow events
          │              │               │
          └──────────────┼───────────────┘
                         ▼
                     EventHub
                         │
               ┌─────────┴─────────┐
               │                   │
               ▼                   ▼
         events.jsonl         live subscribers
                                   │
                                   └── Codex Agent Console
                         │
                         ▼
                 PostCompletion
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
           run.json   summary.md   metrics
                                      │
                                      ▼
                              memory candidates
```

## 5.1 Runtime event examples

```json
{"seq":1,"type":"run.started","ts":"...","run_id":"run-123"}
{"seq":2,"type":"resolver.completed","ts":"...","run_id":"run-123"}
{"seq":3,"type":"workflow.step.started","step_id":"load-context","ts":"..."}
{"seq":4,"type":"agent.item.started","ts":"..."}
{"seq":5,"type":"tool.started","payload":{"tool":"shell"},"ts":"..."}
{"seq":6,"type":"tool.completed","payload":{"exit_code":0},"ts":"..."}
{"seq":7,"type":"workflow.step.completed","step_id":"validate","ts":"..."}
{"seq":8,"type":"run.completed","ts":"..."}
```

## 5.2 Suggested initial event vocabulary

Keep the vocabulary small:

```text
run.started
run.completed
run.failed
run.cancelled

resolver.completed

workflow.started
workflow.completed
workflow.step.queued
workflow.step.started
workflow.step.progress
workflow.step.completed
workflow.step.failed

agent.started
agent.message.delta
agent.message.completed
agent.completed

tool.started
tool.completed
tool.failed

artifact.created
file.changed

background.started
background.progress
background.completed
background.failed

error
```

Do not create dozens of event classes.

Use one `RuntimeEvent` with typed names.

---

# 6. Run Storage Layout

Recommended:

```text
.agent-state/
└── logs/
    └── <session-id>/
        └── <run-id>/
            ├── run.json
            ├── events.jsonl
            ├── summary.md
            ├── artifacts.json
            └── memory_candidates.json
```

Session metadata:

```text
.agent-state/
└── sessions/
    └── <session-id>/
        └── session.json
```

Cache:

```text
.agent-state/cache/
```

Use cache only for derived data such as:

- parsed agent registry;
- repository scan fingerprints;
- reusable context lookup results.

Do not use `.agent-state` as the source of truth for:

- agent instructions;
- workflows;
- skills;
- architectural decisions.

Those remain declarative/version-controlled.

---

# 7. Memory Refactoring

Current proposal:

```text
memory/
├── memory_service.py
├── memory_types.py
├── memory_policy.py
├── memory_extractor.py
├── ingestion/
├── retrieval/
│   ├── retriever.py
│   ├── hybrid_search.py
│   └── reranker.py
├── embeddings/
│   ├── embedding_provider.py
│   ├── local_provider.py
│   ├── bedrock_provider.py
│   └── openai_provider.py
└── stores/
    ├── memory_store.py
    ├── pgvector_store.py
    ├── agentcore_store.py
    └── s3_vector_store.py
```

This is too much code for the current stage.

Recommended:

```text
memory/
├── service.py
├── retrieval.py
├── ingestion/
│   └── .gitkeep
├── embeddings/
│   └── README.md
└── stores/
    └── README.md
```

---

## 7.1 `memory/service.py`

Merge:

- `memory_service.py`
- `memory_types.py`
- `memory_policy.py`
- current placeholder extraction policy

Responsibilities:

```python
class MemoryService:
    def retrieve(...): ...
    def should_extract(...): ...
    def prepare_candidates(...): ...
```

Initial `prepare_candidates()` can safely return no candidates.

Do not call an LLM simply because a run completed.

---

## 7.2 `memory/retrieval.py`

Merge:

- `retriever.py`
- `hybrid_search.py`
- `reranker.py`

for now.

Initial implementation can support:

```text
path filtering
+ keyword/lexical search
+ recency/metadata weighting
```

Later:

```text
lexical
+ vector
+ reranking
```

can be added behind the same interface.

Only split the modules after there is enough code that the concepts have truly separate implementations.

---

## 7.3 `embeddings/`

Keep the directory, but no Python implementation yet.

Use:

```text
embeddings/README.md
```

Document the future contract:

```python
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
```

Future providers may include:

```text
local
Bedrock
OpenAI
```

Do not create three empty provider classes now.

---

## 7.4 `stores/`

Keep the directory, but no Python implementation yet.

Document possible adapters:

```text
pgvector
AgentCore
S3 vector storage
```

Do not create one empty class per possible future backend.

---

# 8. Remove `packages/agent-memory-sdk/` for Now

Recommendation:

> Remove or defer `packages/agent-memory-sdk/`.

Reason:

The current system has one Python runtime that owns memory.

An SDK becomes valuable when at least one of these becomes true:

- another repository needs to call memory independently;
- non-Python clients need a stable memory API;
- memory becomes a separately deployed service;
- agent implementations directly consume memory over a public contract.

Until then:

```text
runtime memory service
```

is enough.

Creating an SDK now would duplicate:

- models;
- request/response types;
- packaging;
- versioning;
- tests;
- documentation.

Reintroduce it only when a real external consumer exists.

---

# 9. Agent Definition Pattern

An agent directory should contain configuration and instructions, not a Python mini-application.

Example:

```text
agents/
└── agent-builder/
    ├── agent.yaml
    └── instructions.md
```

Example `agent.yaml`:

```yaml
version: 1

id: agent-builder
name: Agent Builder

instructions: instructions.md

workflow: build-agent

skills:
  - project-context
  - agent-design
  - verify-output

tools:
  - repo
  - shell
  - web_search

model_profile: standard
```

The resolver loads this configuration.

The runtime invokes it.

No `agent_builder.py` is needed unless the agent needs deterministic custom behavior that cannot be represented by the shared runtime.

---

# 10. `project-registry.yaml`

This should be the small repository-wide control-plane configuration.

Example:

```yaml
version: 1

paths:
  agents: agents
  workflows: workflows/workflow-orchestrator.yaml
  state: .agent-state

runtime:
  default_workflow: default
  max_parallel_tasks: 3

codex:
  command: codex app-server
  working_directory: .

memory:
  enabled: true
  semantic_retrieval: false
  extraction: false

console:
  enabled: true
```

Avoid duplicating every agent into this file.

Agents should be discovered from:

```text
agents/*/agent.yaml
```

The registry should contain global locations and runtime defaults, not a second copy of agent configuration.

---

# 11. Workflow Orchestration

Create one initial file:

```text
workflows/workflow-orchestrator.yaml
```

Do not create a workflow directory with many tiny YAML files yet.

Split later only when this file becomes difficult to navigate.

---

## 11.1 Initial workflow model

Recommended primitive step types:

```text
agent
tool
shell
hook
parallel
```

Recommended simple controls:

```text
when
retry
timeout
depends_on
```

Do not implement a custom programming language inside YAML.

Use named condition flags produced by the resolver/runtime.

Example:

```yaml
version: 1

workflows:

  default:
    steps:

      - id: resolve-context
        name: Load project context
        uses: tool
        tool: project_context

      - id: plan
        name: Plan work
        uses: agent
        agent: planner-agent
        when: needs_planning

      - id: web-research
        name: Search external sources
        uses: tool
        tool: web_search
        when: needs_web_search

      - id: execute
        name: Execute selected agent
        uses: agent
        agent: $resolved_agent

      - id: validate
        name: Validate changes
        uses: parallel
        tasks:
          - id: typecheck
            uses: shell
            command: $validation.typecheck
          - id: tests
            uses: shell
            command: $validation.tests

      - id: finalize
        name: Finalize run
        uses: hook
        hook: post_completion
```

---

## 11.2 Agent Builder workflow

Example:

```yaml
  build-agent:
    steps:

      - id: understand
        name: Understand request
        uses: agent
        agent: planner-agent

      - id: load-context
        name: Load project context
        uses: tool
        tool: project_context

      - id: web-research
        name: Research only if needed
        uses: tool
        tool: web_search
        when: needs_web_search

      - id: design
        name: Design agent
        uses: agent
        agent: agent-builder

      - id: ui
        name: Generate UI mockup
        uses: agent
        agent: agent-ui-builder
        when: needs_ui

      - id: validate
        name: Validate generated agent
        uses: shell
        command: $validation.agent

      - id: finalize
        name: Finalize
        uses: hook
        hook: post_completion
```

---

# 12. Web Search Policy

Web search should be resolved, not automatic.

Set:

```text
needs_web_search = true
```

when one or more apply:

- user explicitly requests research/current information;
- framework/library/API behavior may have changed;
- a current compatibility question matters;
- external specification/documentation is required;
- unfamiliar third-party behavior cannot be established from the repository;
- factual freshness can change the implementation.

Set:

```text
needs_web_search = false
```

for:

- repository structure;
- local code behavior;
- local tests;
- project conventions;
- implementation already represented in source/config/docs.

The workflow should simply contain:

```yaml
when: needs_web_search
```

Do not let each agent independently decide to perform redundant web searches.

The resolver determines whether the capability should be made available to the workflow.

---

# 13. Run Context

Avoid separate:

```text
context.py
skills.py
lifecycle.py
models.py
```

Use one small run context owned by the runtime.

Conceptually:

```python
@dataclass
class RunContext:
    run_id: str
    session_id: str
    prompt: str
    resolved: ResolvedRunSpec
    project_root: Path
    artifacts: list[Path] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
```

This object moves through:

```text
resolver
→ workflow
→ agents/tools
→ post-completion
```

Do not create DTO layers between every internal function.

---

# 14. Custom Codex Agent Console

The HTML mockup should become a design reference.

Production implementation should be a terminal-native UI.

Recommended:

```text
Python
+ Textual
+ Codex App Server
+ asyncio
```

Do not implement the console in TypeScript unless it later becomes a browser/Electron application.

Keeping it in Python allows:

```text
console
→ gateway
→ runtime
```

as direct in-process calls.

No HTTP service is required for the local CLI.

---

# 15. Console Structure

Keep only:

```text
agent-console/
├── console.py
└── console.tcss
```

### `console.py`

Initially contain:

```text
CodexAgentConsole
WorkflowPanel
ActivityPanel
BackgroundTasksPanel
PromptController
```

in one file.

Do not split every widget into a separate Python file.

Split only after the console becomes difficult to navigate, for example when `console.py` exceeds roughly 500–700 meaningful lines.

### `console.tcss`

Keep layout/style separate because it is naturally independent from behavior.

This file should reproduce the visual system from the HTML mockup:

- dark terminal surface;
- 3px border radius;
- compact top bar;
- 3-column workspace;
- workflow progress on left;
- current activity + tabs in center;
- background/queued tasks on right;
- prompt at bottom;
- compact footer.

---

# 16. Console Layout Mapping

The current mockup contains these main surfaces:

```text
┌─────────────────────────────────────────────────────────────┐
│ Codex Agent Console                         time            │
├─────────────────────────────────────────────────────────────┤
│ Agent | Model | Session                          Active     │
├──────────────┬───────────────────────┬──────────────────────┤
│ Workflow     │ Current Activity      │ Background Tasks     │
│              │                       │                      │
│ step 1 ✓     │ Logs | Code | Diff    │ File Search          │
│ step 2 ✓     │ Preview               │ Codex Agent          │
│ step 3 ◌     │                       │ Type Check            │
│ step 4 ○     │ streaming output      │                      │
│ ...          │                       │ queued tasks         │
├──────────────┴───────────────────────┴──────────────────────┤
│ › prompt                                                    │
├─────────────────────────────────────────────────────────────┤
│ runtime | local mode | help | settings | exit              │
└─────────────────────────────────────────────────────────────┘
```

Textual widget mapping:

| Mockup area | Suggested Textual primitive |
|---|---|
| overall layout | Grid / Containers |
| workflow list | custom `Static` rows or `ListView` |
| active spinner | `LoadingIndicator` or small custom spinner |
| workflow progress | `ProgressBar` |
| logs | `RichLog` |
| Code/Diff/Preview | `TabbedContent` |
| code/diff text | `TextArea` / `RichLog` |
| background tasks | custom rows + `ProgressBar` |
| prompt | `TextArea` |
| footer | `Footer` or custom `Static` |
| reactive status | Textual reactive attributes |

---

# 17. Console Event Flow

The terminal UI should be passive.

It renders runtime state.

```text
user types prompt
       │
       ▼
console.py
       │
       ▼
AgentGateway.run(...)
       │
       ▼
AgentRuntime
       │
       ▼
EventHub.emit(...)
       │
       ├── persist event
       │
       └── publish event
                │
                ▼
           console.py
                │
        update reactive state
                │
                ▼
             render
```

The UI should not:

- implement workflow decisions;
- determine agent routing;
- parse log files;
- calculate final metrics;
- own Codex session state.

That belongs to the runtime.

---

# 18. Recommended Gateway API

Use an async iterator.

Example:

```python
class AgentGateway:

    async def run(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
        ...
```

Console:

```python
async for event in gateway.run(prompt):
    self.apply_event(event)
```

This gives the CLI live updates without:

- polling;
- websocket;
- local HTTP API;
- Redis;
- filesystem watchers.

If a web UI is added later, a FastAPI adapter can expose the same event stream through SSE/WebSocket without changing the runtime.

---

# 19. Background Tasks

The mockup contains:

```text
Running
Queued
Completed
```

Use `asyncio.Task`.

The runtime keeps:

```python
background_tasks: dict[str, asyncio.Task]
```

Each task emits:

```text
background.started
background.progress
background.completed
background.failed
```

The console groups tasks based on event state.

Do not create a dedicated Python scheduler module until task management grows beyond simple in-process concurrency.

---

# 20. Workflow UI State

The workflow engine should emit:

```text
workflow.step.queued
workflow.step.started
workflow.step.progress
workflow.step.completed
workflow.step.failed
```

The console maps states to the existing design:

```text
queued     → empty circle
running    → spinner
completed  → green tick
failed     → red/error marker
```

Progress bars should be driven from event payload:

```json
{
  "type": "workflow.step.progress",
  "step_id": "validate",
  "payload": {
    "progress": 0.62,
    "message": "Running type check"
  }
}
```

No UI-specific event types are needed.

---

# 21. Codex App Server Adapter

The custom console is a real client of the Codex harness.

Recommended lifecycle:

```text
console/runtime starts
      │
      ▼
launch `codex app-server`
      │
      ▼
initialize handshake
      │
      ▼
create/resume Codex thread
      │
      ▼
start turn
      │
      ▼
receive item/turn notifications
      │
      ▼
normalize to RuntimeEvent
      │
      ├── console
      └── events.jsonl
```

Important:

- pin/test a supported Codex version for the project;
- keep raw Codex protocol handling behind the runtime;
- the rest of the application should never depend on raw Codex field names;
- normalize Codex events into the project's stable `RuntimeEvent`.

This protects the workflow/UI from protocol changes.

---

# 22. Why Not the TypeScript Codex SDK Here?

A TypeScript SDK can be useful when the surrounding application is TypeScript.

For this architecture it would create:

```text
Python workflow runtime
        │
        ▼
Node/TypeScript bridge
        │
        ▼
Codex
```

That introduces:

- second runtime;
- IPC;
- process supervision;
- duplicate types;
- package management;
- more deployment/setup logic.

Because the custom TUI and orchestration layer are already well suited to Python, a Python JSONL client for Codex App Server is simpler.

Use TypeScript where it naturally belongs:

- browser UI generated by `agent-ui-builder`;
- Angular/React applications;
- Node services;
- TypeScript artifacts created by agents.

Do not use TypeScript merely because a library exists in TypeScript.

---

# 23. CLI Commands

Keep the CLI surface simple.

Initial commands:

```text
agent-console
agent-console --agent agent-builder
agent-console --session <session-id>
agent-console --resume
```

Inside the TUI:

```text
Enter            submit prompt
Shift+Enter      new line
Ctrl+C           cancel active work / exit when idle
Tab              move panel focus
?                help
```

Optional later:

```text
/agent
/workflow
/session
/clear
/resume
/logs
```

Do not reproduce all Codex CLI commands initially.

Expose only features your console actually needs.

---

# 24. Agent Resolution Flow

Recommended:

```text
USER PROMPT
    │
    ▼
gateway.py
    │
    ▼
resolver.py
    │
    ├── classify task
    ├── choose agent
    ├── choose workflow
    ├── choose skills
    ├── needs planning?
    ├── needs web?
    └── choose verification
    │
    ▼
ResolvedRunSpec
    │
    ▼
workflow.py
```

The resolver should return data.

It should not execute the run itself.

---

# 25. Complete Runtime Flow

```text
User
 │
 ▼
Codex Agent Console
 │
 ▼
AgentGateway
 │
 ▼
bootstrap/runtime
 │
 ▼
Resolver
 │
 ├── selected agent
 ├── workflow
 ├── skills
 ├── context queries
 ├── tool policy
 └── web-search flag
 │
 ▼
WorkflowEngine
 │
 ├── load project context
 │
 ├── optional planner-agent
 │
 ├── optional web search
 │
 ├── execute target agent through Codex App Server
 │
 ├── validations/background tasks
 │
 └── finalize
 │
 ▼
EventHub
 │
 ├── console updates
 └── events.jsonl
 │
 ▼
PostCompletion
 │
 ├── run.json
 ├── summary.md
 ├── artifacts.json
 ├── metrics
 └── memory_candidates.json
```

---

# 26. Agent Builder Flow

```text
Prompt:
"Build an agent for X"
       │
       ▼
resolver
       │
       ├── agent = agent-builder
       ├── workflow = build-agent
       └── needs_ui = optional
       │
       ▼
planner-agent
       │
       ▼
project context
       │
       ├── existing agents
       ├── reusable skills
       ├── existing workflow patterns
       └── registry conventions
       │
       ▼
optional web research
       │
       ▼
agent-builder
       │
       ├── agent.yaml
       ├── instructions.md
       └── workflow changes if necessary
       │
       ▼
optional agent-ui-builder
       │
       └── HTML UI mockup
       │
       ▼
validate
       │
       ▼
post-completion
```

---

# 27. Agent UI Builder

The `agent-ui-builder` should initially be simple.

It can generate:

```text
HTML
CSS
small JavaScript
```

for UI mockups.

Do not turn it into a frontend framework generator immediately.

Its initial purpose:

> Quickly visualize an agent's intended user interaction before implementation.

Example outputs:

```text
artifacts/
└── ui/
    ├── index.html
    └── preview.json
```

For the custom terminal UI itself, however, use the real Python Textual implementation rather than the generated HTML mockup.

---

# 28. Shared Models Without `models.py` Explosion

Do not create:

```text
gateway/models.py
runtime/models.py
workflow/models.py
logging/models.py
memory/models.py
console/models.py
```

For internal-only structures, keep dataclasses close to their owner.

Examples:

```text
ResolvedRunSpec → resolver.py
RuntimeEvent    → events.py
RunContext      → runtime.py
MemoryHit       → memory/retrieval.py
```

Only create a shared `models.py` later when:

- the same data model is imported by several independently meaningful modules;
- moving it removes a circular dependency;
- it is part of a stable public contract.

---

# 29. Provider Abstractions

Do not create `providers.py` initially.

Current provider:

```text
Codex App Server
```

Implement one concrete adapter.

Extract a provider abstraction only when the runtime actually supports at least two meaningful execution backends, for example:

```text
Codex App Server
OpenAI Responses direct
local model harness
```

Premature provider interfaces often produce more code than value.

---

# 30. Skill Loading

Do not create a dedicated runtime service unless needed.

Agent config contains:

```yaml
skills:
  - project-context
  - verify-change
```

Registry resolves them to paths.

Resolver chooses relevant skills.

Runtime includes selected skill references/instructions when starting the Codex turn.

That can initially be implemented with small helper functions in:

```text
registry.py
resolver.py
runtime.py
```

Extract `skills.py` only when skill resolution itself becomes complex.

---

# 31. Project Context

Do not create a `context.py` initially.

Use a few reusable functions associated with the resolver/runtime:

```python
def build_context_queries(...)
async def collect_project_context(...)
def compact_context(...)
```

If context retrieval later becomes a major subsystem with:

- multiple sources;
- token budgets;
- semantic search;
- context packs;
- ranking;

then create:

```text
context/
```

At the current stage, that is premature.

---

# 32. Lifecycle

Do not create `lifecycle.py`.

Lifecycle is already represented by events:

```text
run.started
...
run.completed
run.failed
run.cancelled
```

Runtime owns transitions.

Post-completion owns finalization.

A separate lifecycle service would duplicate those responsibilities.

---

# 33. Error Handling

Use one domain exception hierarchy only if needed.

Initially, ordinary Python exceptions plus normalized events are enough.

Example:

```python
try:
    ...
except Exception as exc:
    await events.emit(
        RuntimeEvent(
            type="error",
            ...,
            payload={
                "exception": type(exc).__name__,
                "message": str(exc),
            },
        )
    )
    raise
```

Do not create one custom exception per subsystem unless callers need to make a different recovery decision.

---

# 34. Retry Policy

Workflow YAML can define:

```yaml
retry:
  max_attempts: 2
```

Runtime supports retry only for explicitly retryable steps.

Do not retry:

- user cancellation;
- invalid configuration;
- deterministic schema failure with unchanged input;
- permission denial without changed permissions.

Always emit each attempt.

Example:

```text
workflow.step.started attempt=1
workflow.step.failed attempt=1
workflow.step.started attempt=2
workflow.step.completed attempt=2
```

---

# 35. Cancellation

Maintain one cancellation mechanism in the runtime.

Conceptually:

```python
cancel_event = asyncio.Event()
```

All workflow loops check it.

The console's Ctrl+C behavior:

```text
active run?
    yes → request cancellation
    no  → exit console
```

Do not implement separate cancellation logic for:

- agent;
- workflow;
- tool;
- console.

Use one run-level cancellation signal and cancel child tasks.

---

# 36. Metrics

Derive metrics from events after the run.

Do not instrument a second metrics state machine.

Examples:

```text
run duration
step duration
agent duration
tool duration
number of retries
number of tool calls
validation result
files changed
background task count
```

Post-completion can calculate these by reading event timestamps.

---

# 37. Artifacts

Any generated file should emit:

```text
artifact.created
```

Example payload:

```json
{
  "path": "agents/new-agent/agent.yaml",
  "kind": "agent-definition"
}
```

`artifacts.json` becomes an index derived from those events.

Do not maintain an independent artifact registry during execution unless later required.

---

# 38. Source-of-Truth Rules

Use this priority:

```text
user instruction
      ↓
current repository code/config/tests
      ↓
agent.yaml / workflow YAML
      ↓
maintained architecture/ADR
      ↓
durable project memory
      ↓
runtime session history
```

Runtime logs are evidence.

They are not application configuration.

---

# 39. Git Policy

Recommended:

Commit:

```text
agents/
workflows/
agent-gateway/
agent-runtime/
agent-console/
project-registry.yaml
pyproject.toml
docs/
```

Ignore most runtime state:

```gitignore
.agent-state/cache/*
.agent-state/logs/*
.agent-state/sessions/*
!.agent-state/cache/.gitkeep
!.agent-state/logs/.gitkeep
!.agent-state/sessions/.gitkeep
```

Do not commit raw run logs to the application repository.

---

# 40. `pyproject.toml`

Prefer one Python project configuration.

Do not create separate `requirements.txt` files for gateway/runtime/console unless deployment boundaries later require them.

Initial dependencies can remain small:

```text
PyYAML
Textual
```

Use Python standard library for:

```text
asyncio
subprocess
json
pathlib
dataclasses
logging helpers
```

Avoid adding:

```text
Celery
Redis
FastAPI
SQLAlchemy
Pydantic
Temporal
Prefect
```

until a real requirement appears.

A local terminal application does not need an HTTP framework.

---

# 41. Testing Strategy

Keep tests by behavior, not one test file per Python module.

Suggested:

```text
tests/
├── test_resolver.py
├── test_workflow_runtime.py
├── test_events_and_finalization.py
└── test_console_state.py
```

Integration smoke test:

```text
prompt
→ resolver
→ mock Codex transport
→ workflow events
→ post completion
→ expected run artifacts
```

Do not create dozens of unit tests that simply mirror tiny functions.

---

# 42. Codex Transport Testability

Runtime should accept a transport/client dependency.

Example conceptual constructor:

```python
AgentRuntime(
    codex_client=codex_client,
    events=event_hub,
    memory=memory_service,
)
```

Tests inject:

```python
FakeCodexClient
```

This lets workflow/runtime tests run without launching real Codex.

No heavyweight mocking framework is required.

---

# 43. Incremental Implementation Plan

## Phase 1 — Structural refactor

1. Create the refined directories.
2. Reduce `agent-gateway` to `gateway.py`.
3. Merge registry + loader.
4. Merge logging into `events.py`.
5. Merge memory core files.
6. remove placeholder embedding/store Python files.
7. remove/defer `agent-memory-sdk`.

Acceptance:

```text
imports are simple
no circular dependencies
configuration loads
existing agents are discoverable
```

---

## Phase 2 — Resolver

Implement:

```text
prompt
→ selected agent
→ selected workflow
→ selected skills
→ web-search flag
→ planning flag
```

Start with explicit rules and configuration.

Do not use semantic embeddings yet.

---

## Phase 3 — EventHub

Implement:

```text
emit
append JSONL
subscribe/unsubscribe
load run
```

Verify events remain available if a run crashes before completion.

---

## Phase 4 — Workflow engine

Implement:

```text
ordered steps
conditions
retry
parallel group
cancellation
```

No general DAG compiler.

---

## Phase 5 — Codex integration

Implement the structured Codex client through App Server.

Tasks:

1. launch child process;
2. initialize protocol;
3. create/resume thread;
4. start turn;
5. consume streamed notifications;
6. normalize events;
7. support cancellation/approval as required;
8. close cleanly.

Pin/test the Codex CLI version used by the project.

---

## Phase 6 — Post-completion

Produce:

```text
run.json
summary.md
artifacts.json
memory_candidates.json
```

Derive metrics from events.

---

## Phase 7 — Console

Implement the layout from `codex-agent-console-ui-mockup.html`.

Order:

1. static Textual layout;
2. prompt input;
3. event subscription;
4. workflow progress;
5. logs;
6. background tasks;
7. Code/Diff/Preview tabs;
8. cancellation;
9. session resume.

---

## Phase 8 — Agent Builder

Implement `agent-builder` end to end:

```text
prompt
→ resolve
→ plan
→ context
→ optional web
→ generate agent files
→ validate
→ summary
```

Do not build all planned agents first.

Use Agent Builder itself to create additional agents after the core runtime works.

---

## Phase 9 — Agent UI Builder

Implement a simple HTML mockup generator.

Do not create a production frontend framework yet.

---

## Phase 10 — Memory retrieval

Initial:

```text
lexical search
metadata
path filtering
```

Later:

```text
semantic embeddings
hybrid search
reranking
```

Implement the later stages only after memory volume shows a real need.

---

# 44. Refactoring Checklist

Before creating any new `.py` file, ask:

1. Does this file own a meaningful lifecycle or subsystem?
2. Will it contain enough behavior to justify an import boundary?
3. Does another existing module already own this responsibility?
4. Is this merely a single dataclass/interface?
5. Is this abstraction supporting more than one real implementation?
6. Is this a future placeholder rather than current code?
7. Would keeping the code near its caller make the system easier to understand?

If the answer suggests the file is conceptual only:

> do not create it.

---

# 45. Split Thresholds

Compact does not mean giant files forever.

Use these rough signals to extract a module:

### Extract when

- a file exceeds roughly 500–700 meaningful lines;
- two parts have independent lifecycles;
- an abstraction has two real implementations;
- tests repeatedly need one component independently;
- circular dependencies begin to appear;
- the module becomes difficult to explain in one sentence.

### Do not extract merely because

- one class exists;
- a design diagram has a named box;
- there may be another provider someday;
- a future feature might need it;
- a framework tutorial uses that structure.

---

# 46. Anti-Patterns to Avoid

## 46.1 One file per noun

Avoid:

```text
context.py
context_types.py
context_loader.py
context_policy.py
context_provider.py
```

before there is enough context logic to justify a subsystem.

---

## 46.2 Wrapper calling wrapper

Avoid:

```text
gateway
→ lifecycle
→ runtime manager
→ provider manager
→ provider
→ client
```

Prefer:

```text
gateway
→ runtime
→ Codex client
```

---

## 46.3 UI polling log files

Avoid:

```text
runtime → file
UI → poll file
```

Prefer:

```text
runtime → EventHub → UI
                 └→ file
```

---

## 46.4 Planner for every prompt

Avoid:

```text
prompt → planner LLM → resolver → executor LLM
```

for trivial work.

Prefer:

```text
prompt → deterministic resolver
                 │
                 └→ planner only when needed
```

---

## 46.5 Semantic infrastructure before semantic need

Avoid implementing:

```text
embedding provider hierarchy
vector stores
reranker hierarchy
ingestion workers
```

while there are only a small number of memory files.

Preserve the directories, not the unnecessary code.

---

## 46.6 Python/TypeScript duplication

Avoid implementing the same:

```text
Run
Event
Workflow
Agent config
```

types in both languages.

Python owns the control plane.

Generated browser UI artifacts may use TypeScript independently.

---

# 47. Final Architecture Principles

The project should feel like this:

```text
Definitions are files.
Execution is Python.
Codex is a structured child runtime.
Workflows are YAML.
Events are the common language.
Logs are append-only facts.
Post-hooks derive summaries.
The console renders events.
Memory is progressive.
Abstractions appear only after real duplication.
```

The architecture should not feel like this:

```text
every concept = package
every noun = class
every future possibility = interface
every workflow = Python module
every provider = stub
every event = event class
every UI state = duplicated state store
```

---

# 48. Final Recommended File Ownership Matrix

| Concern | Source of truth |
|---|---|
| agent identity/config | `agents/<agent>/agent.yaml` |
| agent instructions | `agents/<agent>/instructions.md` |
| global project paths/defaults | `project-registry.yaml` |
| workflows | `workflows/workflow-orchestrator.yaml` |
| external entry point | `agent-gateway/gateway.py` |
| dependency wiring | `bootstrap.py` |
| config discovery | `registry.py` |
| task resolution | `resolver.py` |
| execution/Codex | `runtime.py` |
| workflow state | `workflow.py` |
| live + persisted facts | `events.py` |
| run finalization | `post_completion.py` |
| memory behavior | `memory/service.py` |
| memory lookup | `memory/retrieval.py` |
| terminal UX | `agent-console/console.py` |
| terminal styling | `agent-console/console.tcss` |
| transient state | `.agent-state/` |

---

# 49. Initial Definition of Done

The refined first version is complete when a user can run:

```text
agent-console
```

enter:

```text
Create an agent that reviews Angular routing changes.
```

and observe:

```text
1. Resolver selects agent-builder.
2. Workflow appears in the left panel.
3. Context loading appears as a workflow/background task.
4. Planner runs only if needed.
5. Web search runs only if resolver enabled it.
6. Codex agent execution streams into Logs.
7. Code/Diff/Preview updates appear in the center.
8. Typecheck/tests appear in Background Tasks.
9. Completed workflow steps turn into green ticks.
10. Runtime writes events.jsonl continuously.
11. A crash still leaves partial event history.
12. PostCompletion generates run.json, summary.md and artifacts.json.
13. memory_candidates.json exists but memory extraction remains disabled.
14. No redundant gateway/runtime/logging/memory Python layers exist.
```

---

# 50. Recommended Immediate Refactor

Apply these changes before adding more functionality:

```text
DELETE / MERGE
────────────────────────────────────────────
agent-gateway/models.py
agent-gateway/loader.py
agent-gateway/runtime.py
agent-gateway/lifecycle.py
agent-gateway/memory.py
agent-gateway/skills.py
agent-gateway/context.py
agent-gateway/providers.py

logging/event_logger.py
logging/event_store.py
logging/event_types.py

memory/memory_types.py
memory/memory_policy.py
memory/memory_extractor.py

memory/retrieval/hybrid_search.py
memory/retrieval/reranker.py

memory/embeddings/*.py
memory/stores/*.py

packages/agent-memory-sdk/
```

Replace with:

```text
KEEP / CREATE
────────────────────────────────────────────
agent-gateway/gateway.py

agent-runtime/agent-monorepo/bootstrap.py
agent-runtime/agent-monorepo/registry.py
agent-runtime/agent-monorepo/resolver.py
agent-runtime/agent-monorepo/runtime.py
agent-runtime/agent-monorepo/workflow.py
agent-runtime/agent-monorepo/events.py
agent-runtime/agent-monorepo/post_completion.py

agent-runtime/agent-monorepo/memory/service.py
agent-runtime/agent-monorepo/memory/retrieval.py
agent-runtime/agent-monorepo/memory/embeddings/README.md
agent-runtime/agent-monorepo/memory/stores/README.md

workflows/workflow-orchestrator.yaml

agent-console/console.py
agent-console/console.tcss
```

This gives the architecture clear boundaries while remaining intentionally small.

---

# 51. Closing Decision

The most important architectural choice is:

> **Do not model every concept as a file. Model stable execution boundaries as files.**

For this project, those stable boundaries are:

```text
gateway
registry
resolver
runtime
workflow
events
finalization
memory
console
```

Everything else should remain:

```text
configuration
functions
dataclasses
or future placeholders
```

until real complexity earns a new module.
