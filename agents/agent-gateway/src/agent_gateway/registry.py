from __future__ import annotations

from pathlib import Path

import yaml

from .models import AgentSpec


_RESERVED = {
    "agent-gateway",
    "agent-runtime",
    "skills",
    "memory",
    "evaluations",
    ".agent-state",
}


class AgentRegistry:
    def __init__(self, monorepo_root: Path):
        self.monorepo_root = monorepo_root.resolve()
        self.agents_root = (self.monorepo_root / "agents").resolve()
        if not self.agents_root.is_dir():
            raise FileNotFoundError(f"Agents root not found: {self.agents_root}")

    def path_for(self, agent_id: str) -> Path:
        path = (self.agents_root / agent_id).resolve()
        if path.parent != self.agents_root:
            raise ValueError("Agent path must be a direct child of agents/.")
        return path

    def exists(self, agent_id: str) -> bool:
        path = self.path_for(agent_id)
        spec_path = path / "agent.yaml"
        if not path.is_dir() or not spec_path.is_file():
            return False
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        return not raw.get("disabled", False)

    def list_agents(self) -> list[str]:
        result: list[str] = []
        for child in self.agents_root.iterdir():
            if not child.is_dir() or child.name in _RESERVED:
                continue
            spec_path = child / "agent.yaml"
            if child.name.startswith("agent-") and spec_path.is_file():
                raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
                if raw.get("disabled", False):
                    continue
                result.append(child.name)
        return sorted(result)

    def read_spec(self, agent_id: str) -> AgentSpec:
        path = self.path_for(agent_id) / "agent.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"agent.yaml not found for {agent_id}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        spec = AgentSpec.model_validate(raw)
        if spec.disabled:
            raise RuntimeError(f"Agent is disabled: {agent_id}")
        return spec
