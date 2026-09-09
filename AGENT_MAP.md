# Monorepo Agent Map

This file is the human- and Codex-readable map of the agent platform. Machine-readable project metadata lives in `project-registry.yaml`.

## Platform boundary

All agent implementations and agent-related platform artifacts live under `agents/`.

## Registered V1 projects / agents

The V1 agents are currently disabled while the agent set is being rebuilt.
Disabled agents remain on disk for reference, but the resolver and gateway must
not select or load them.

### agent-builder

- Path: `agents/agent-builder`
- Status: disabled
- Purpose: Design, validate, scaffold, and register new agents.
- Runtime: `agents/agent-gateway`
- Primary output: A versioned `agents/agent-<name>/` directory containing machine-readable configuration, instructions, skills, and evaluation criteria.

### agent-ui-builder

- Path: `agents/agent-ui-builder`
- Status: disabled
- Purpose: Build UI artifacts for agent applications.
- V1 scope: A lightweight standalone HTML mockup for the Agent Builder experience.

## Shared platform components

### agent-runtime/agent-monorepo

Selects a project/agent before loading a worker. V1 uses deterministic resolution. `semantic_search.py` is intentionally empty and reserved for the local semantic resolver.

### agent-gateway

Common control-plane package for agent build/load/run/resume behavior. Agent-specific code must not reimplement runtime, registry, or filesystem materialization logic.

## V1 routing rule

1. Read `project-registry.yaml`.
2. Ignore disabled projects.
3. Resolve exactly one project.
4. Load exactly one corresponding enabled agent through `AgentGateway`.
5. Do not load unrelated agent instructions, skills, or memory.

## Naming rule

Agent directories are normalized to `agent-<name>`. Existing V1 projects already use that form (`agent-builder`, `agent-ui-builder`), so do not create names such as `agent-agent-builder`.
