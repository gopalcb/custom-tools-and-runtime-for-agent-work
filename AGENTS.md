# Agent Monorepo Guidance

This repository uses the refined architecture defined by
`refined-agent-monorepo-architecture-workflow-codex-console.md`.

- Treat `agents/*/agent.yaml`, each agent's `instructions.md`,
  `project-registry.yaml`, and
  `agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml` with its
  adjacent `workflow-steps.yaml` as the version-controlled sources of truth.
- Keep the gateway a thin facade. Resolution, execution, Codex protocol,
  workflow state, events, finalization, and memory access belong to
  `agent-runtime/agent-monorepo/`.
- Use the shared `RuntimeEvent` contract for live console state and persisted
  facts. Never make the console poll JSONL logs.
- Keep new agents declarative. Add custom Python only for proven deterministic
  behavior that the shared runtime and YAML workflow cannot express.
- Keep Codex changes inside the configured workspace-write roots. The local
  default approval policy is `never`, so normal in-repository work should not
  pause for permission prompts.
- Run `.venv/bin/python -m pytest -q` and the compile checks after runtime or
  workflow changes. Use a fake Codex transport for normal automated tests.
- Do not add speculative provider hierarchies, vector stores, schedulers,
  duplicate model layers, or a Python/TypeScript bridge.

## Python projects

Whenever you create, review, refactor, or extend Python code, read and follow
`agents/skills/python-coder/SKILL.md` before editing. Keep each Python project
documented with `ARCHITECTURE.md` and `code-map.yaml`, keep those files in sync
with Python structure changes, and run the relevant compile and test checks.
