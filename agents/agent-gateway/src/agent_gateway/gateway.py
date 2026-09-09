from __future__ import annotations

from pathlib import Path

from .builder import AgentFilesystemBuilder
from .loader import AgentLoader
from .models import AgentRunResult, AgentSpec, LoadedAgent
from .registry import AgentRegistry
from .runtime import AgentRuntime


class AgentGateway:
    """Stable facade for agent lifecycle operations."""

    def __init__(self, monorepo_root: str | Path):
        self.monorepo_root = Path(monorepo_root).resolve()
        self.registry = AgentRegistry(self.monorepo_root)
        self.loader = AgentLoader(self.registry)
        self.builder = AgentFilesystemBuilder(self.registry)
        self.runtime = AgentRuntime(self.monorepo_root)

    def list_agents(self) -> list[str]:
        return self.registry.list_agents()

    def load(self, agent_id: str) -> LoadedAgent:
        return self.loader.load(agent_id)

    def validate(self, agent_id: str) -> AgentSpec:
        loaded = self.loader.load(agent_id)
        if not loaded.instructions.strip():
            raise ValueError(f"{agent_id} has empty instructions.")
        return loaded.spec

    def build(self, spec: AgentSpec, *, template_dir: str | Path, template_context: dict, overwrite: bool = False) -> Path:
        return self.builder.build(
            spec,
            template_dir=Path(template_dir),
            template_context=template_context,
            overwrite=overwrite,
        )

    def run(self, agent_id: str, prompt: str) -> AgentRunResult:
        return self.runtime.run(self.load(agent_id), prompt)

    def resume(self, agent_id: str, session_id: str, prompt: str) -> AgentRunResult:
        return self.runtime.resume(self.load(agent_id), session_id, prompt)
