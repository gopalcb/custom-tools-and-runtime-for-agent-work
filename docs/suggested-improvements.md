# Suggested Improvements

Last reviewed: 2026-09-10

## Current Readiness

The repo now has the right core direction for autonomous project work:

- Native Codex CLI remains the terminal default.
- Root `AGENTS.md` defines the project behavior and `/codex-agent` fallback.
- `agent-monorepo` is the default agent in `project-registry.yaml`.
- Runtime state, events, finalization, and memory live in
  `agent-runtime/agent-monorepo/`.
- Memory candidates are generated from logs and made retrievable locally.
- The obsolete Python `agent-console` package is no longer needed and has been
  removed from packaging and tests.

The largest remaining gaps are around project onboarding, memory quality,
validation rigor, and stale generated artifacts.

## Immediate Cleanup

- Update or remove stale docs that still refer to old console/mockup work. The
  README has been corrected in this pass, but untracked or deleted planning
  artifacts should be reviewed before committing.
- Restore the tracked `.agent-state/*/.gitkeep` files if the state directory
  skeleton should remain version controlled.
- Remove local generated files from commits: `.DS_Store`, `__pycache__`,
  `.pytest_cache`, logs, Angular cache, `node_modules`, and built `dist`
  outputs should stay ignored.
- Decide whether `agent-tools/codex-sdk-client` and `agent-tools/web-search`
  are active supported packages. If yes, include them in validation and package
  docs. If no, mark them deprecated or remove them.
- Clarify the difference between the native Codex CLI version policy in
  `project-registry.yaml` and the `openai-codex` Python SDK package pin in
  `pyproject.toml` and `agent-tools/codex-sdk-client/requirements.txt`.
- Add `ARCHITECTURE.md` and `code-map.yaml` for declarative agents that have
  Python-adjacent behavior or become project-critical.

## Before Building Projects

Create a standard `projects/` scaffold before the first real project lands:

```text
projects/<project-id>/
|-- AGENTS.md
|-- ARCHITECTURE.md
|-- code-map.yaml
|-- project.yaml
|-- README.md
`-- tests/
```

`project.yaml` should include:

- project ID and display name;
- stack and package manager;
- default agent and fallback agent;
- validation commands;
- dev server commands;
- deployment target;
- memory namespace;
- source directories;
- generated directories to ignore;
- external integrations and source-of-truth docs.

Add resolver support for project scope so a request about one project retrieves
that project's memory first.

## Memory Improvements

- Add memory schema versioning and explicit memory kinds.
- Separate raw candidates from accepted durable memory.
- Add promotion, deduplication, redaction, conflict resolution, and stale
  memory handling.
- Add memory evaluation queries with expected top results.
- Track prompt token usage from retrieved memory.
- Add a user-visible memory audit report.
- Add project-scoped memory namespaces before `projects/` grows.
- Keep JSON as the source of truth; add OpenSearch only as an index when local
  retrieval quality or volume demands it.

## Workflow And Agent Improvements

- Add tests that prove normal requests run planning first and explicit
  skip-planning requests bypass it.
- Add tests that prove `/codex-agent` selects the generic fallback agent.
- Add workflow-level validation for all referenced tools, agent IDs, shell
  commands, conditions, retries, and timeouts.
- Add a small workflow simulation command that can print the selected steps for
  a prompt without running Codex.
- Add a health check that validates native Codex path resolution, CLI version
  range, registry load, workflow load, state paths, and memory read/write.
- Add an ADR documenting the native Codex CLI decision and retired Python
  console.

## Controller UI Improvements

`agent-runtime/monorepo-controller` appears to be a separate browser controller,
not the removed Python `agent-console`. Keep it only if it has a clear role:

- live RuntimeEvent inspection;
- memory browser and audit UI;
- run history viewer;
- workflow visualization;
- agent registry and health dashboard.

If it stays, it should not poll JSONL logs or duplicate runtime state. It
should consume runtime/gateway APIs and the shared `RuntimeEvent` contract.

## Validation Improvements

- Make the registry validation commands the canonical CI commands.
- Add TypeScript/Nest/Angular build checks for `agent-runtime/monorepo-controller`
  if that app remains supported.
- Add tests for log-derived memory candidates using real fixture events.
- Add tests for memory retrieval path containment and metadata filters.
- Add a packaging/import smoke test for every supported Python tool package.
- Add a no-live-Codex integration suite with fake App Server transport.

## Documentation Improvements

- Add `docs/native-codex-routing.md` for root `AGENTS.md`, `bin/codex`, and
  `/codex-agent` behavior.
- Add `docs/runtime-event-contract.md` with event types, required fields, and
  examples.
- Add `docs/project-onboarding.md` for new `projects/` work.
- Add `docs/memory-record-schema.md` once schema versioning lands.
- Add ADRs for decisions that agents must not repeatedly rediscover.

## Recommended Priority

1. Finish cleanup and commit the native CLI plus removed Python console state.
2. Add project scaffolding and project-scoped resolver/memory metadata.
3. Harden memory schema, promotion, redaction, and retrieval budget.
4. Add health checks and workflow simulation.
5. Add memory retrieval evaluations.
6. Decide whether `monorepo-controller` is a supported UI and validate it in CI
   if it is.
7. Add OpenSearch hybrid retrieval only after local memory volume or quality
   justifies the infrastructure.
