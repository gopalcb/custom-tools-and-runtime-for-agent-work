from __future__ import annotations

from pathlib import Path

import yaml

from .models import LoadedAgent
from .registry import AgentRegistry


class AgentLoader:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def load(self, agent_id: str) -> LoadedAgent:
        spec = self.registry.read_spec(agent_id)
        root = self.registry.path_for(agent_id)

        instructions_path = root / spec.instructions_file
        skills_path = root / spec.skills_file
        evals_path = root / spec.evals_file

        instructions = instructions_path.read_text(encoding="utf-8")
        skills_raw = yaml.safe_load(skills_path.read_text(encoding="utf-8")) or {}
        evals = yaml.safe_load(evals_path.read_text(encoding="utf-8")) or {}

        skills: list[str] = []
        for key in ("always", "relevant"):
            skills.extend(skills_raw.get("skills", {}).get(key, []) or [])

        return LoadedAgent(
            spec=spec,
            root=root,
            instructions=instructions,
            skills=list(dict.fromkeys(skills)),
            evaluations=evals,
        )
