from __future__ import annotations

from pathlib import Path

from .models import AgentDesign


class AgentDesignValidator:
    def validate(self, design: AgentDesign, *, agents_root: Path, overwrite: bool = False) -> AgentDesign:
        if design.agent_id in {"agent-gateway", "agent-runtime"}:
            raise ValueError(f"Reserved agent id: {design.agent_id}")
        if len(design.purpose.strip()) < 8:
            raise ValueError("Purpose is too short to define a useful agent.")
        if not design.responsibilities:
            raise ValueError("At least one responsibility is required.")
        if not design.workflow_steps:
            raise ValueError("At least one workflow step is required.")
        if not design.evaluation_requirements:
            raise ValueError("At least one evaluation requirement is required.")

        destination = (agents_root / design.agent_id).resolve()
        if destination.parent != agents_root.resolve():
            raise ValueError("Generated agent must be a direct child of agents/.")
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Agent already exists: {design.agent_id}")
        return design
