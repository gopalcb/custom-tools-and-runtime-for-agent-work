# Agent Gateway

Shared control-plane package used by all monorepo agents.

Responsibilities:
- materialize a validated agent specification into `agents/agent-<name>/`
- load agent configuration/instructions/skills/evals
- enforce monorepo/agents filesystem boundaries for build operations
- run or resume agents through a provider adapter
- expose stable models so agent projects do not depend on provider internals

V1 provider: Codex via the official `openai-codex` Python package (optional dependency).
