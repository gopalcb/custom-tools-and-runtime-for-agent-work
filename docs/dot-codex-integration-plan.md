# .codex Integration Plan

Last reviewed: 2026-09-11

## Implementation Status

Implemented on 2026-09-11:

- `.codex/config.toml` was added with project-scoped native Codex defaults.
- `.codex/agents/standard.toml` and `.codex/agents/deep.toml` were added as
  native Codex custom subagents.
- `AGENTS.md` was updated with native Codex subagent routing guidance.
- The old hook logger and Git push scripts were intentionally not imported.

## Decision

Bring a **minimal project-scoped `.codex/`** into this monorepo, but do not copy
the old `.codex` directory wholesale.

Recommended outcome:

- add `.codex/config.toml` for native Codex CLI defaults that mirror this
  repository's trusted local automation posture;
- add `.codex/agents/standard.toml` and `.codex/agents/deep.toml` after adapting
  their instructions to this monorepo's runtime, workflow, memory, and
  validation contracts;
- do not import the old hooks or Git push scripts until they are rewritten to
  avoid absolute paths and to use this repo's `RuntimeEvent`/`.agent-state`
  artifact model;
- do not set committed project defaults to full dangerous access. Keep the repo
  default at `approval_policy = "never"` plus `sandbox_mode = "workspace-write"`.
  Use a personal profile or explicit CLI flag for full access when the operator
  intentionally wants it.

This gives the native Codex CLI better local defaults and useful subagent roles
without duplicating the existing YAML planning workflow or weakening the repo's
control-plane boundaries by default.

## Why This Is The Right Scope

Official OpenAI documentation separates the relevant surfaces:

- `AGENTS.md` is the durable instruction surface. Codex loads global guidance
  from `~/.codex/AGENTS.md` and project guidance from repository `AGENTS.md`
  files, with closer files overriding broader ones:
  <https://learn.chatgpt.com/docs/agent-configuration/agents-md>.
- `.codex/config.toml` is the project-scoped configuration surface for trusted
  repositories. It can set model, reasoning, approval, sandbox, MCP, hooks, and
  related defaults:
  <https://learn.chatgpt.com/docs/config-file/config-basic>.
- `.codex/agents/*.toml` can define custom local Codex subagents with their own
  `model`, `model_reasoning_effort`, and `developer_instructions`:
  <https://learn.chatgpt.com/docs/agent-configuration/subagents>.
- The sandbox and approval docs distinguish removing approval prompts from
  removing the sandbox. `approval_policy = "never"` avoids pauses, while
  `sandbox_mode = "danger-full-access"` removes the execution boundary and is
  meant for deliberate full-access operation:
  <https://learn.chatgpt.com/docs/agent-approvals-security>.

This repo already has repository guidance in `AGENTS.md`, a project registry
with `codex.approval_policy: never`, `codex.sandbox: workspace-write`, and a
planning workflow (`analyze`, `resolve-context`, optional `web-research`,
`plan`) before normal execution. The new `.codex` layer should support the
native CLI experience, not become a second runtime.

## Old `.codex` Review

Source reviewed:
`/Users/gopalcbala/Desktop/WORK_N_PROJECTS/monorepo/old.project/agentic-web-dev/.codex`.

### Useful To Adapt

`config.toml`

- Sets low-friction native Codex defaults: model, reasoning effort, verbosity,
  token limits, compaction, and subagent settings.
- Useful conceptually, but it should be updated for this monorepo and current
  model guidance before being copied.

`agents/standard.toml`

- Good fit for ordinary implementation work.
- Matches the `context-standard` style already useful here: focused retrieval,
  nearest tests, small coherent changes, escalate when broader architecture or
  history is required.
- Should be adapted to explicitly honor this repo's `AGENTS.md`, runtime
  source-of-truth files, and validation commands.

`agents/deep.toml`

- Good fit for architecture changes, cross-system failures, migrations,
  security/auth, concurrency/state issues, and difficult incidents.
- Should be adapted to this repo's `context-deep` process and the shared
  runtime's event/memory contracts.

### Do Not Copy As-Is

`hooks.json` and `hooks/session_logger.py`

- The hook commands contain absolute paths to the old
  `agentic-web-dev` checkout.
- The logger writes a separate Markdown session log under the old project's
  `.agent/session-logs` path.
- This monorepo already defines durable run artifacts under
  `.agent-state/logs/<session>/<run>/` and derives work-memory records from
  `RuntimeEvent` records. A second hook-based transcript logger would duplicate
  state and conflict with the repository guidance that clients should not poll
  or duplicate runtime state.

`scripts/push-agentic-web-dev.sh`

- Hard-codes the old GitHub repository and replacement-push workflow.
- Not appropriate for this monorepo.

`scripts/validate-git-push-target.sh` and `git-push-repo-allowlist.txt`

- The allowlist concept is useful, but the old allowlist only permits
  `agentic-autonomous-web-dev-workflow`.
- If this repo needs push protection, implement it as a repo-specific hook or
  rule with this monorepo's actual remote names and without old project paths.

## Recommended `.codex/config.toml`

Start with a conservative project config:

```toml
#:schema https://developers.openai.com/codex/config-schema.json

# Native Codex CLI defaults for this trusted monorepo.
model = "gpt-6-astra"
model_reasoning_effort = "low"
model_verbosity = "low"
model_reasoning_summary = "concise"

approval_policy = "never"
sandbox_mode = "workspace-write"
tool_output_token_limit = 8000

skills.max_context_tokens = 4000

model_auto_compact_token_limit = 200000
model_auto_compact_token_limit_scope = "total"

[sandbox_workspace_write]
network_access = true
writable_roots = ["."]

[agents]
enabled = true
max_concurrent_threads_per_session = 2
default_subagent_model = "gpt-6-astra"
default_subagent_reasoning_effort = "medium"
interrupt_message = false
```

Notes:

- `approval_policy = "never"` is consistent with `project-registry.yaml` and
  prevents routine permission prompts.
- `workspace-write` keeps writes bounded to the repo by default.
- Use `gpt-6-astra` only if the local account/CLI has access. If availability or
  cost is a concern, use the current Codex default or a lower-cost current
  coding model, then keep the standard/deep split through reasoning effort.
- Avoid committing `sandbox_mode = "danger-full-access"` as the project default.
  If full access is needed, create a personal, untracked profile in `~/.codex`
  and launch Codex with that profile for intentional high-trust sessions.

## Recommended Custom Agents

Keep two project custom agents in `.codex/agents/`:

### `standard`

Purpose:

- ordinary bugs, features, tests, focused refactors, and known subsystem work.

Suggested settings:

```toml
name = "standard"
model = "gpt-6-astra"
model_reasoning_effort = "medium"
model_verbosity = "low"
model_reasoning_summary = "concise"
approval_policy = "never"
```

Instruction changes from the old file:

- refer to this monorepo's `AGENTS.md` and `agent-config/agents/agent-monorepo/instructions.md`;
- use `context-standard`;
- keep edits scoped to the runtime, workflow, agent, event, finalization, or
  memory boundary implied by the task;
- run the repo's compile/test commands after Python/runtime changes;
- return a compact handoff if the work needs `deep`.

### `deep`

Purpose:

- architecture changes, cross-system failures, auth/security issues,
  migrations, difficult incidents, major refactors, and state/concurrency
  problems.

Suggested settings:

```toml
name = "deep"
model = "gpt-6-astra"
model_reasoning_effort = "high"
model_verbosity = "low"
model_reasoning_summary = "concise"
approval_policy = "never"
```

Instruction changes from the old file:

- use `context-deep`;
- retrieve architecture, ADR/history, runtime logs, and memory only when each
  source answers a specific uncertainty;
- preserve the shared `RuntimeEvent` contract;
- do not introduce duplicate provider layers, schedulers, vector stores, or a
  Python/TypeScript bridge;
- de-escalate back to focused implementation once the problem is narrow.

## Complexity Selection Behavior

The old `standard` and `deep` agents can help this repo, but they do not replace
the existing planner by themselves.

Expected behavior after adding them:

- In native Codex CLI sessions, Codex can spawn `standard` or `deep` subagents
  when the user asks directly or when repo instructions request delegation.
- Their descriptions and TOML settings give Codex a clearer way to choose model
  and reasoning effort for delegated work.
- The current shared runtime still selects declarative agents and workflows from
  `project-registry.yaml`, `agent-config/agents/*/agent.yaml`, and
  `agent-runtime/agent-monorepo/workflows/*.yaml`.

Therefore, also update root `AGENTS.md` with a short routing rule:

```md
## Native Codex Subagent Routing

- Use `standard` for ordinary non-trivial repository engineering tasks.
- Use `deep` for architecture changes, cross-system failures, auth/security
  issues, migrations, difficult incidents, major refactors, or state/concurrency
  problems.
- Keep the main thread responsible for final decisions, edits, validation, and
  user-facing summary unless the user explicitly asks for parallel execution.
```

Do not add a second custom planner in `.codex`. The repo already has a planning
workflow with an implementation planner agent.

## Full Access Policy

Do not make dangerous full access the committed default.

Recommended layers:

- Project default: `.codex/config.toml` with `approval_policy = "never"` and
  `sandbox_mode = "workspace-write"`.
- Runtime default: keep `project-registry.yaml` aligned with `approval_policy:
  never`, `sandbox: workspace-write`, `network_access: true`, and
  `writable_roots: [.]`.
- Personal escape hatch: create `~/.codex/full-access.config.toml` outside the
  repo when needed:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

Then launch with:

```bash
codex --profile full-access
```

This preserves the user's desire for no routine permission prompts while keeping
the repository safe for future runs, subagents, and automation.

## Implementation Steps

1. Create `.codex/config.toml` with the conservative defaults above.
2. Create `.codex/agents/standard.toml` and `.codex/agents/deep.toml` by
   adapting the old agent instructions to this repo.
3. Add the short native subagent routing section to root `AGENTS.md`.
4. Do not add hooks in the first pass.
5. If session hooks are later desired, design them against `.agent-state` and
   `RuntimeEvent` records, then document how they differ from existing runtime
   finalization.
6. If push protection is needed, create a monorepo-specific allowlist/rule and
   test it independently from Codex session startup.

## Verification

After implementation, verify:

```bash
codex --ask-for-approval never "Summarize active project config and instruction sources."
codex --ask-for-approval never "List available custom agents and when you would use standard vs deep."
.venv/bin/python -m compileall agent-runtime/agent-monorepo agent-gateway agent-tools/internal-messaging agent-tools/ui-debugger agent-config/agents/agent-implementation-planner agent-config/agents/agent-logs-analyzer
.venv/bin/python -m pytest -q
```

If `.codex` is protected as read-only under the active sandbox after creation,
future updates to `.codex` may require an explicit trusted edit path or a
temporary full-access session.

## Final Recommendation

Proceed with the minimal `.codex` integration. It is useful for native Codex CLI
defaults and for standard/deep subagent capacity. Do not use it to replace this
monorepo's declarative runtime, workflow YAML, event contract, finalization
artifacts, or memory system.
