from __future__ import annotations

from pathlib import Path

from .models import AgentRunResult, LoadedAgent
from .providers.codex import CodexProvider
from .providers.openai_agents import OpenAIAgentsProvider


class AgentRuntime:
    def __init__(self, monorepo_root: Path):
        self.monorepo_root = monorepo_root.resolve()

    def _provider(self, agent: LoadedAgent):
        if agent.spec.runtime.provider == "codex":
            return CodexProvider()
        if agent.spec.runtime.provider == "openai-agents":
            return OpenAIAgentsProvider()
        raise ValueError(f"Unsupported provider: {agent.spec.runtime.provider}")

    def _cwd(self, agent: LoadedAgent) -> Path:
        cwd = (self.monorepo_root / agent.spec.runtime.workspace).resolve()
        if self.monorepo_root != cwd and self.monorepo_root not in cwd.parents:
            raise ValueError("Runtime workspace escapes monorepo root.")
        if not cwd.exists():
            raise FileNotFoundError(f"Runtime workspace not found: {cwd}")
        return cwd

    def run(self, agent: LoadedAgent, prompt: str) -> AgentRunResult:
        return self._provider(agent).run_new(agent, prompt, cwd=self._cwd(agent))

    def resume(self, agent: LoadedAgent, session_id: str, prompt: str) -> AgentRunResult:
        return self._provider(agent).resume(agent, session_id, prompt, cwd=self._cwd(agent))
