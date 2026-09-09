# Change Plan

## Findings

- `AgentGateway.list_agents()` returns no working agents because both concrete agent specs are marked `disabled: true`.
- `AgentGateway.load("agent-builder")` fails with `RuntimeError: Agent is disabled: agent-builder`.
- `project-registry.yaml` also disables both agent projects, so the runtime resolver cannot route to them.
- The Codex provider loads its optional SDK before entering its failure-result guard, so a missing `openai-codex` dependency raises instead of returning `AgentRunResult(status="failed")`.
- No minimal local tests exist for the gateway loading path, the agent-builder scaffold path, or deterministic runtime resolution.
- `pytest` is not installed in the local Python environment, so the smoke tests should use the standard-library `unittest` runner.

## Changes

1. Enable `agent-builder` and `agent-ui-builder` by setting `disabled: false` in their `agent.yaml` files and `project-registry.yaml`.
2. Add standard-library smoke tests under `agents/tests/` that:
   - verify registered agents are listed, loadable, and validate through `AgentGateway`;
   - verify `AgentBuilderService.preview()` does not write files;
   - verify `AgentBuilderService.build()` creates a loadable scaffold in a temporary monorepo fixture;
   - verify building an existing agent without overwrite fails safely.
3. Keep Codex runtime startup failures inside the provider result contract so missing optional dependencies produce a failed `AgentRunResult`.
4. Add resolver/provider smoke coverage that does not call Codex or the network.

## Validation

Run:

```bash
PYTHONPATH=agents/agent-builder/src:agents/agent-gateway/src python3 -m unittest discover -s agents/tests -v
```
