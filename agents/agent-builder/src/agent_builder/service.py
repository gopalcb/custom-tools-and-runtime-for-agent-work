from __future__ import annotations

from pathlib import Path

from agent_gateway import AgentGateway
from agent_gateway.models import AgentSpec, PermissionConfig, RuntimeConfig

from .designer import AgentDesigner
from .models import AgentBuildRequest, AgentBuildResult, AgentDesign
from .validator import AgentDesignValidator


class AgentBuilderService:
    def __init__(self, monorepo_root: str | Path):
        self.monorepo_root = Path(monorepo_root).resolve()
        self.agents_root = (self.monorepo_root / "agents").resolve()
        self.agent_root = self.agents_root / "agent-builder"
        self.template_dir = self.agent_root / "templates"
        self.gateway = AgentGateway(self.monorepo_root)
        self.designer = AgentDesigner()
        self.validator = AgentDesignValidator()

    def preview(self, request: AgentBuildRequest) -> AgentDesign:
        design = self.designer.design(request)
        # Preview validates semantic structure but deliberately ignores destination existence.
        return self.validator.validate(design, agents_root=self.agents_root, overwrite=True)

    def build(self, request: AgentBuildRequest) -> AgentBuildResult:
        design = self.designer.design(request)
        self.validator.validate(design, agents_root=self.agents_root, overwrite=request.overwrite)

        spec = AgentSpec(
            id=design.agent_id,
            description=design.description,
            purpose=design.purpose,
            runtime=RuntimeConfig(provider="codex", sandbox="workspace-write", workspace="agents"),
            permissions=PermissionConfig(
                filesystem_read=design.filesystem_read,
                filesystem_write=design.filesystem_write,
                shell=design.shell,
                network=design.network,
            ),
        )

        context = {
            "spec": spec.model_dump(),
            "design": design.model_dump(),
        }
        destination = self.gateway.build(
            spec,
            template_dir=self.template_dir,
            template_context=context,
            overwrite=request.overwrite,
        )

        # Reload through the same runtime contract to catch malformed generated artifacts.
        self.gateway.validate(design.agent_id)

        return AgentBuildResult(
            agent_id=design.agent_id,
            path=str(destination.relative_to(self.monorepo_root)),
            created_files=["agent.yaml", "AGENT.md", "skills.yaml", "evals.yaml"],
            message=f"Created and validated {design.agent_id}.",
        )
