from __future__ import annotations

from .base import AgentProvider


class OpenAIAgentsProvider(AgentProvider):
    """Reserved provider adapter.

    V1 intentionally uses Codex only. Implement this adapter later without changing
    agent definitions or gateway call sites.
    """

    def run_new(self, agent, prompt, *, cwd):
        raise NotImplementedError("OpenAI Agents provider is not implemented in V1.")

    def resume(self, agent, session_id, prompt, *, cwd):
        raise NotImplementedError("OpenAI Agents provider is not implemented in V1.")
