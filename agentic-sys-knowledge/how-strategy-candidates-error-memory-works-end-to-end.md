# How Strategy, Candidates, Error, and Memory Works End to End

## Purpose

The memory system has two jobs:

- derive factual run memory from completed runtime events;
- preserve user strategy feedback so future agents can adapt how they work.

Error tracking is separate from memory injection. Errors are operational state
under internal messaging until fixed, while selected memory records are
retrieved into future agent instructions.

## Durable Locations

Run evidence and candidate artifacts:

```text
.agent-state/logs/<session-id>/<run-id>/
  events.jsonl
  run.json
  summary.md
  metrics.json
  artifacts.json
  memory_candidates.json
```

Retrievable memory records:

```text
.agent-state/cache/memory/records/
```

Strategy feedback memory:

```text
.agent-state/cache/memory/records/strategy/
```

Operational error state:

```text
.agent-state/agents-messaging/current-error.json
.agent-state/agents-messaging/errors/
```

System diagnostic logs:

```text
.agent-state/logs/system/runtime/
.agent-state/logs/system/messaging/
.agent-state/logs/system/controller/
.agent-state/logs/system/health/
```

## Run Memory Candidate Lifecycle

1. The runtime emits `RuntimeEvent` objects throughout a run.
2. `EventHub` persists those events under:

   ```text
   .agent-state/logs/<session-id>/<run-id>/events.jsonl
   ```

3. After a terminal event, `post_completion.finalize_run()` loads the persisted
   events once.
4. Finalization writes run artifacts: `run.json`, `summary.md`, `metrics.json`,
   `artifacts.json`, and `memory_candidates.json`.
5. `MemoryService.prepare_candidates()` deterministically derives candidates
   from events when extraction is enabled.
6. Accepted records are stored under `.agent-state/cache/memory/records/`.

Current candidate kinds include:

- `run-summary`: prompt, status, resolved agent, workflow, changed files,
  artifacts, failures, and final message.
- `failure-summary`: unique failed step, tool, background, and error messages.
- `change-summary`: changed files and created artifacts.

Candidate generation uses persisted events. It does not require a model call or
embedding call.

## Strategy Feedback Lifecycle

Strategy feedback is controlled by `memory.strategy_feedback` in
`project-registry.yaml`.

1. Execution workflows run `store-strategy-memory` after work/validation and
   before finalization.
2. The runtime hook calls `StrategyFeedbackCoordinator.collect_feedback()`.
3. The Tkinter feedback form asks the user for feedback, optional rework, and
   whether durable strategy memory should be stored.
4. The submitted feedback is written as a run artifact.
5. The `strategy-memory-analyzer` agent classifies the feedback and proposes
   deterministic memory actions.
6. `MemoryService.apply_strategy_memory_actions()` validates and writes active
   strategy records under:

   ```text
   .agent-state/cache/memory/records/strategy/
   ```

7. If the analyzer returns no memory action while storage was requested, the
   runtime uses a local fallback action so submitted feedback still becomes
   durable strategy memory.
8. If feedback requests rework, the runtime runs a bounded rework turn and then
   asks for feedback again.

Older strategy records are not deleted when replaced. They are marked
`superseded` so the system keeps history without injecting stale guidance.

## Retrieval Into Future Agent Context

Before a Codex agent step starts, `AgentRuntime._assembled_instructions()` calls:

```python
context.memory_service.retrieve_context(context.prompt)
```

`MemoryService.retrieve_context()`:

1. loads stored memory records;
2. skips records with status `superseded`, `rejected`, or `needs_review`;
3. ranks active records through `MemoryRetriever`;
4. returns a compact text block, default limit 5;
5. truncates each hit to 2,400 characters.

The runtime injects that block into developer instructions under:

```text
# Retrieved project memory
```

If there are no relevant hits, the runtime injects:

```text
No relevant project memory was retrieved.
```

## Retrieval Ranking

`MemoryRetriever` uses local lexical scoring plus metadata and recency weights.
It only accepts record paths that resolve under the configured memory root.
Semantic/vector retrieval is not part of the current runtime.

Current behavior:

- no external memory service;
- no vector store;
- no embedding dependency;
- bounded prompt injection;
- current source and current user instructions remain more authoritative than
  retrieved memory.

## Error Memory Versus Operational Errors

Operational errors are not injected as long-term learning by default. They are
tracked through internal messaging so the controller and agents can see an
active problem immediately.

Error lifecycle:

1. Runtime emits an error event, or the log analyzer sees a fresh `ERROR` line.
2. The exact error object is sent to `MessageBus.record_error()`.
3. The bus writes or updates:

   ```text
   .agent-state/agents-messaging/current-error.json
   ```

4. The bus also sends an `error.detected` message with the exact error object as
   its payload.
5. The messaging portal shows active errors.
6. After a fix is verified, `agent-msg resolve-error` archives the active error
   under:

   ```text
   .agent-state/agents-messaging/errors/
   ```

If a recurring error becomes a useful project lesson, it should later be
captured as a memory record through normal memory extraction or strategy
feedback. The active error file itself is operational state, not the primary
long-term learning store.

## Health Check

Before work starts, `system_health.py` checks required local services and state:

- project registry;
- agent definitions;
- runtime session logs;
- runtime sessions;
- runtime, messaging, controller, and health diagnostic directories;
- memory records directory;
- log analyzer program when configured;
- internal messaging manifest, event log, and error archive.

Latest health artifact:

```text
.agent-state/logs/system/health/latest.json
```

If health is unhealthy, the checker records
`monorepo_system_health.failed` through internal messaging so the error remains
visible until fixed.

## Validation

Use these checks after memory, strategy, or error changes:

```bash
.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-tools/internal-messaging agent-config/agents/agent-logs-analyzer
.venv/bin/python -m pytest -q tests/test_strategy_feedback.py tests/test_system_health.py tests/test_log_analyzer.py tests/test_internal_messaging_bus.py
.venv/bin/python -m agent_monorepo.system_health --project-root .
```
