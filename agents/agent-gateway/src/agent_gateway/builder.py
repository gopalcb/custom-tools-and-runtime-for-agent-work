from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .models import AgentSpec
from .registry import AgentRegistry


class AgentAlreadyExistsError(RuntimeError):
    pass


class AgentFilesystemBuilder:
    """Materializes an already-designed AgentSpec.

    This class deliberately does not decide what an agent should do. Design belongs
    to `agent-builder`; this layer only performs bounded filesystem operations.
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def build(
        self,
        spec: AgentSpec,
        *,
        template_dir: Path,
        template_context: dict,
        overwrite: bool = False,
    ) -> Path:
        destination = self.registry.path_for(spec.id)
        if destination.exists() and not overwrite:
            raise AgentAlreadyExistsError(f"Agent already exists: {spec.id}")

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )

        rendered = {
            "agent.yaml": env.get_template("agent.yaml.j2").render(**template_context),
            "AGENT.md": env.get_template("AGENT.md.j2").render(**template_context),
            "skills.yaml": env.get_template("skills.yaml.j2").render(**template_context),
            "evals.yaml": env.get_template("evals.yaml.j2").render(**template_context),
        }

        with TemporaryDirectory(prefix="agent-build-") as tmp:
            staging = Path(tmp) / spec.id
            staging.mkdir(parents=True)
            for name, content in rendered.items():
                (staging / name).write_text(content, encoding="utf-8")

            # Validate the rendered machine config before changing the repository.
            import yaml
            from .models import AgentSpec as _AgentSpec

            _AgentSpec.model_validate(yaml.safe_load((staging / "agent.yaml").read_text(encoding="utf-8")))

            if destination.exists():
                for child in destination.iterdir():
                    if child.is_file():
                        child.unlink()
                # V1 overwrite intentionally refuses recursive cleanup of arbitrary dirs.
            else:
                destination.mkdir(parents=False)

            for source in staging.iterdir():
                (destination / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        return destination
