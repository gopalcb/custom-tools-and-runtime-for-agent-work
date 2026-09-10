"""Load and validate the monorepo's declarative agents, skills, and workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from .workflows.workflow_resolver import WorkflowConfigurationError, resolve_step_references


_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STEP_USES = frozenset({"agent", "tool", "shell", "hook", "parallel"})


class RegistryError(ValueError):
    """Raised when a declarative project definition is missing or unsafe."""


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    instructions_path: Path
    instructions: str
    workflow: str
    skills: tuple[str, ...]
    skill_paths: tuple[Path, ...]
    tools: tuple[str, ...]
    model_profile: str | None = None
    aliases: tuple[str, ...] = ()


class Registry:
    """Load, validate, and cache all declarative project definitions."""

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path = "project-registry.yaml",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        if not self.project_root.is_dir():
            raise RegistryError(f"Project root does not exist: {self.project_root}")

        self.config_path = self._safe_path(config_path, self.project_root, "project registry")
        self._project_config: dict[str, Any] = {}
        self._agents: dict[str, AgentDefinition] = {}
        self._workflows: dict[str, dict[str, Any]] = {}
        self._workflow_steps: dict[str, dict[str, Any]] = {}
        self._skill_cache: dict[str, Path] = {}
        self.reload()

    @property
    def project_config(self) -> dict[str, Any]:
        """Return a copy so callers cannot mutate the cached source of truth."""
        return deepcopy(self._project_config)

    @property
    def agents_root(self) -> Path:
        return self._agents_root

    @property
    def workflows_path(self) -> Path:
        return self._workflows_path

    @property
    def workflow_steps_path(self) -> Path | None:
        """Return the optional reusable workflow-step catalog path."""
        return self._workflow_steps_path

    @property
    def state_root(self) -> Path:
        return self._state_root

    @property
    def messaging_root(self) -> Path:
        """Return the durable root used for inter-agent messages."""
        return self._messaging_root

    def reload(self) -> None:
        """Atomically replace the cache after all definitions validate."""
        config = self._load_yaml(self.config_path, "project registry")
        self._require_keys(config, ("version", "paths", "runtime"), "project registry")
        self._validate_version(config["version"], "project registry")
        paths = self._mapping(config["paths"], "project registry paths")

        agents_root = self._configured_path(paths, "agents", "agents", expect="directory")
        workflows_path = self._configured_path(
            paths,
            "workflows",
            "agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml",
            expect="file",
        )
        workflow_steps_path = self._optional_configured_path(paths, "workflow_steps")
        state_root = self._configured_path(paths, "state", ".agent-state", expect=None)
        messaging_root = self._configured_path(
            paths, "messaging", ".agent-state/agents-messaging", expect=None
        )

        runtime = self._mapping(config["runtime"], "runtime configuration")
        default_workflow = runtime.get("default_workflow")
        if not isinstance(default_workflow, str) or not default_workflow.strip():
            raise RegistryError("runtime.default_workflow must be a non-empty string")
        max_parallel = runtime.get("max_parallel_tasks")
        if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
            raise RegistryError("runtime.max_parallel_tasks must be a positive integer")

        workflow_steps = self._load_workflow_steps(workflow_steps_path)
        workflows = self._load_workflows(workflows_path, workflow_steps)
        if default_workflow not in workflows:
            raise RegistryError(
                f"runtime.default_workflow references unknown workflow: {default_workflow}"
            )

        skill_roots = self._skill_roots(paths, agents_root)
        agents, skill_cache = self._load_agents(agents_root, workflows, skill_roots)
        self._validate_agent_aliases(agents)
        self._validate_workflow_agents(workflows, agents)
        default_agent = runtime.get("default_agent")
        if default_agent is not None and default_agent not in agents:
            raise RegistryError(f"runtime.default_agent references unknown agent: {default_agent}")

        self._project_config = config
        self._agents_root = agents_root
        self._workflows_path = workflows_path
        self._workflow_steps_path = workflow_steps_path
        self._state_root = state_root
        self._messaging_root = messaging_root
        self._workflows = workflows
        self._workflow_steps = workflow_steps
        self._agents = agents
        self._skill_cache = skill_cache

    def get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._agents)) or "none"
            raise RegistryError(f"Unknown agent '{agent_id}'. Available agents: {available}") from exc

    def list_agents(self) -> list[AgentDefinition]:
        return [self._agents[agent_id] for agent_id in sorted(self._agents)]

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        try:
            return deepcopy(self._workflows[workflow_id])
        except KeyError as exc:
            available = ", ".join(sorted(self._workflows)) or "none"
            raise RegistryError(
                f"Unknown workflow '{workflow_id}'. Available workflows: {available}"
            ) from exc

    def execution_workflow_ids(self) -> set[str]:
        """Return workflows that the planner may select after planning."""
        return {
            workflow_id
            for workflow_id, workflow in self._workflows.items()
            if workflow.get("phase", "execution") == "execution"
        }

    def resolve_skill(self, skill_id: str) -> Path:
        try:
            return self._skill_cache[skill_id]
        except KeyError as exc:
            raise RegistryError(f"Unknown skill '{skill_id}'") from exc

    def _configured_path(
        self,
        paths: Mapping[str, Any],
        key: str,
        default: str,
        *,
        expect: str | None,
    ) -> Path:
        value = paths.get(key, default)
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise RegistryError(f"paths.{key} must be a non-empty path")
        path = self._safe_path(value, self.project_root, f"paths.{key}")
        if expect == "directory" and not path.is_dir():
            raise RegistryError(f"paths.{key} directory does not exist: {path}")
        if expect == "file" and not path.is_file():
            raise RegistryError(f"paths.{key} file does not exist: {path}")
        return path

    def _optional_configured_path(self, paths: Mapping[str, Any], key: str) -> Path | None:
        """Resolve an optional project-relative configuration file path."""
        if key not in paths:
            return None
        return self._configured_path(paths, key, "", expect="file")

    def _skill_roots(self, paths: Mapping[str, Any], agents_root: Path) -> tuple[Path, ...]:
        configured = paths.get("skills", agents_root / "skills")
        values = configured if isinstance(configured, list) else [configured]
        if not values or any(not isinstance(value, (str, Path)) for value in values):
            raise RegistryError("paths.skills must be a path or a non-empty list of paths")
        roots = tuple(self._safe_path(value, self.project_root, "paths.skills") for value in values)
        missing = [str(root) for root in roots if not root.is_dir()]
        if missing:
            raise RegistryError(f"Configured skill directory does not exist: {', '.join(missing)}")
        return roots

    def _load_workflow_steps(self, path: Path | None) -> dict[str, dict[str, Any]]:
        """Load the optional catalog of reusable workflow step definitions."""
        if path is None:
            return {}
        document = self._load_yaml(path, "workflow step catalog")
        self._require_keys(document, ("version", "steps"), "workflow step catalog")
        self._validate_version(document["version"], "workflow step catalog")
        raw_steps = self._mapping(document["steps"], "workflow step catalog steps")
        steps: dict[str, dict[str, Any]] = {}
        for step_id, raw_step in raw_steps.items():
            self._validate_identifier(step_id, "workflow step catalog id")
            step = self._mapping(raw_step, f"workflow step catalog step '{step_id}'")
            if step.get("id") != step_id:
                raise RegistryError(f"Workflow step catalog step '{step_id}' must use the same id")
            self._validate_step_shape(step, f"workflow step catalog step '{step_id}'")
            steps[step_id] = deepcopy(step)
        return steps

    def _load_workflows(
        self, path: Path, workflow_steps: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        document = self._load_yaml(path, "workflow definitions")
        self._require_keys(document, ("version", "workflows"), "workflow definitions")
        self._validate_version(document["version"], "workflow definitions")
        raw_workflows = self._mapping(document["workflows"], "workflows")
        if not raw_workflows:
            raise RegistryError("workflows must contain at least one workflow")

        workflows: dict[str, dict[str, Any]] = {}
        for workflow_id, raw in raw_workflows.items():
            self._validate_identifier(workflow_id, "workflow id")
            workflow = self._mapping(raw, f"workflow '{workflow_id}'")
            phase = workflow.get("phase", "execution")
            if phase not in {"planning", "execution"}:
                raise RegistryError(f"workflow '{workflow_id}'.phase must be planning or execution")
            raw_steps = workflow.get("steps")
            if not isinstance(raw_steps, list):
                raise RegistryError(f"workflow '{workflow_id}'.steps must be a list")
            try:
                steps = resolve_step_references(raw_steps, workflow_steps)
            except WorkflowConfigurationError as exc:
                raise RegistryError(f"workflow '{workflow_id}': {exc}") from exc
            if not isinstance(steps, list):
                raise RegistryError(f"workflow '{workflow_id}'.steps must be a list")
            self._validate_steps(steps, f"workflow '{workflow_id}'")
            workflows[workflow_id] = {**deepcopy(workflow), "phase": phase, "steps": steps}
        return workflows

    def _validate_steps(self, steps: list[Any], label: str) -> None:
        ids: set[str] = set()
        for index, raw_step in enumerate(steps):
            step = self._mapping(raw_step, f"{label} step {index + 1}")
            self._validate_step_shape(step, f"{label} step {index + 1}")
            step_id = step["id"]
            uses = step["uses"]
            required_field = {
                "agent": "agent",
                "tool": "tool",
                "shell": "command",
                "hook": "hook",
                "parallel": "tasks",
            }[uses]
            self._validate_identifier(step_id, f"step id in {label}")
            if step_id in ids:
                raise RegistryError(f"Duplicate step id '{step_id}' in {label}")
            ids.add(step_id)
            if uses == "parallel":
                tasks = step["tasks"]
                if not isinstance(tasks, list) or not tasks:
                    raise RegistryError(f"Parallel step '{step_id}' in {label} requires tasks")
                self._validate_steps(tasks, f"parallel step '{step_id}' in {label}")
            elif not isinstance(step[required_field], str) or not step[required_field].strip():
                raise RegistryError(
                    f"Step '{step_id}' in {label}.{required_field} must be a non-empty string"
                )

    @staticmethod
    def _validate_step_shape(step: Mapping[str, Any], label: str) -> None:
        """Validate fields required by a single declarative step."""
        Registry._require_keys(step, ("id", "uses"), label)
        uses = step["uses"]
        if uses not in _STEP_USES:
            raise RegistryError(f"Step '{step.get('id')}' in {label} has unsupported uses: {uses!r}")
        required_field = {
            "agent": "agent",
            "tool": "tool",
            "shell": "command",
            "hook": "hook",
            "parallel": "tasks",
        }[uses]
        if required_field not in step:
            raise RegistryError(f"Step '{step.get('id')}' in {label} missing required field: {required_field}")

    @staticmethod
    def _validate_workflow_agents(
        workflows: Mapping[str, Mapping[str, Any]],
        agents: Mapping[str, AgentDefinition],
    ) -> None:
        for workflow_id, workflow in workflows.items():
            for step in _iter_steps(workflow["steps"]):
                agent_id = step.get("agent")
                if step.get("uses") != "agent" or agent_id == "$resolved_agent":
                    continue
                if agent_id not in agents:
                    raise RegistryError(
                        f"Workflow '{workflow_id}' references unknown agent: {agent_id!r}"
                    )

    def _load_agents(
        self,
        agents_root: Path,
        workflows: Mapping[str, Any],
        skill_roots: tuple[Path, ...],
    ) -> tuple[dict[str, AgentDefinition], dict[str, Path]]:
        agents: dict[str, AgentDefinition] = {}
        skill_cache: dict[str, Path] = {}
        for definition_path in sorted(agents_root.glob("*/agent.yaml")):
            try:
                definition_path.resolve().relative_to(agents_root)
            except ValueError as exc:
                raise RegistryError(
                    f"Agent definition escapes configured agents root: {definition_path}"
                ) from exc
            raw = self._load_yaml(definition_path, f"agent definition {definition_path}")
            if raw.get("disabled", False):
                continue
            self._require_keys(
                raw,
                ("version", "id", "name", "instructions", "workflow", "skills", "tools"),
                f"agent definition {definition_path}",
            )
            self._validate_version(raw["version"], f"agent definition {definition_path}")
            agent_id = raw["id"]
            self._validate_identifier(agent_id, f"agent id in {definition_path}")
            if agent_id != definition_path.parent.name:
                raise RegistryError(
                    f"Agent id '{agent_id}' must match directory '{definition_path.parent.name}'"
                )
            if agent_id in agents:
                raise RegistryError(f"Duplicate agent id: {agent_id}")

            name = raw["name"]
            workflow_id = raw["workflow"]
            if not isinstance(name, str) or not name.strip():
                raise RegistryError(f"Agent '{agent_id}'.name must be a non-empty string")
            if not isinstance(workflow_id, str) or workflow_id not in workflows:
                raise RegistryError(
                    f"Agent '{agent_id}' references unknown workflow: {workflow_id!r}"
                )

            instructions_value = raw["instructions"]
            if not isinstance(instructions_value, str) or not instructions_value.strip():
                raise RegistryError(f"Agent '{agent_id}'.instructions must be a non-empty path")
            instructions_path = self._safe_path(
                instructions_value,
                definition_path.parent,
                f"Agent '{agent_id}' instructions",
                boundary=definition_path.parent,
            )
            if not instructions_path.is_file():
                raise RegistryError(
                    f"Agent '{agent_id}' instructions file does not exist: {instructions_path}"
                )

            skills = self._string_tuple(raw["skills"], f"Agent '{agent_id}'.skills")
            tools = self._string_tuple(raw["tools"], f"Agent '{agent_id}'.tools")
            aliases = self._string_tuple(raw.get("aliases", []), f"Agent '{agent_id}'.aliases")
            resolved_skills: list[Path] = []
            for skill_id in skills:
                path = skill_cache.get(skill_id)
                if path is None:
                    path = self._find_skill(skill_id, skill_roots)
                    skill_cache[skill_id] = path
                resolved_skills.append(path)

            model_profile = raw.get("model_profile")
            if model_profile is not None and not isinstance(model_profile, str):
                raise RegistryError(f"Agent '{agent_id}'.model_profile must be a string or null")
            agents[agent_id] = AgentDefinition(
                id=agent_id,
                name=name.strip(),
                instructions_path=instructions_path,
                instructions=instructions_path.read_text(encoding="utf-8"),
                workflow=workflow_id,
                skills=skills,
                skill_paths=tuple(resolved_skills),
                tools=tools,
                model_profile=model_profile,
                aliases=aliases,
            )
        if not agents:
            raise RegistryError(f"No enabled agent definitions found under {agents_root}")
        return agents, skill_cache

    def _find_skill(self, skill_id: str, roots: tuple[Path, ...]) -> Path:
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise RegistryError("Skill ids must be non-empty strings")
        matches: set[Path] = set()
        for root in roots:
            direct = self._safe_path(skill_id, root, f"skill '{skill_id}'", boundary=root)
            candidates = (direct, direct / "SKILL.md")
            for candidate in candidates:
                if candidate.is_file() and candidate.name == "SKILL.md":
                    matches.add(candidate.resolve())
            if "/" not in skill_id and "\\" not in skill_id:
                for path in root.glob(f"**/{skill_id}/SKILL.md"):
                    resolved = path.resolve()
                    try:
                        resolved.relative_to(root)
                    except ValueError as exc:
                        raise RegistryError(
                            f"Skill '{skill_id}' resolves outside configured skill root: {path}"
                        ) from exc
                    matches.add(resolved)
        if not matches:
            raise RegistryError(f"Skill '{skill_id}' does not resolve to a SKILL.md")
        if len(matches) > 1:
            rendered = ", ".join(str(path) for path in sorted(matches))
            raise RegistryError(f"Skill '{skill_id}' is ambiguous: {rendered}")
        return next(iter(matches))

    def _safe_path(
        self,
        value: str | Path,
        base: Path,
        label: str,
        *,
        boundary: Path | None = None,
    ) -> Path:
        raw_path = Path(value)
        candidate = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise RegistryError(f"{label} escapes project root {self.project_root}: {value}") from exc
        if boundary is not None:
            try:
                candidate.relative_to(boundary.resolve())
            except ValueError as exc:
                raise RegistryError(f"{label} escapes allowed root {boundary}: {value}") from exc
        return candidate

    @staticmethod
    def _validate_agent_aliases(agents: Mapping[str, AgentDefinition]) -> None:
        claimed: dict[str, str] = {}
        for agent in agents.values():
            for alias in (agent.id, agent.name, *agent.aliases):
                normalized = " ".join(alias.casefold().split())
                owner = claimed.get(normalized)
                if owner is not None and owner != agent.id:
                    raise RegistryError(
                        f"Agent selection phrase '{alias}' is shared by '{owner}' and '{agent.id}'"
                    )
                claimed[normalized] = agent.id

    @staticmethod
    def _load_yaml(path: Path, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise RegistryError(f"{label.capitalize()} file does not exist: {path}")
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise RegistryError(f"Unable to load {label} from {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise RegistryError(f"{label.capitalize()} must contain a YAML mapping: {path}")
        return value

    @staticmethod
    def _mapping(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise RegistryError(f"{label.capitalize()} must be a mapping")
        return value

    @staticmethod
    def _require_keys(value: Mapping[str, Any], keys: tuple[str, ...], label: str) -> None:
        missing = [key for key in keys if key not in value]
        if missing:
            raise RegistryError(f"{label.capitalize()} missing required fields: {', '.join(missing)}")

    @staticmethod
    def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise RegistryError(f"{label} must be a list of non-empty strings")
        if len(value) != len(set(value)):
            raise RegistryError(f"{label} must not contain duplicates")
        return tuple(value)

    @staticmethod
    def _validate_identifier(value: Any, label: str) -> None:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise RegistryError(f"Invalid {label}: {value!r}; use lowercase kebab-case")

    @staticmethod
    def _validate_version(value: Any, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise RegistryError(f"{label.capitalize()}.version must be a positive integer")


def _iter_steps(steps: list[Any]):
    for step in steps:
        yield step
        tasks = step.get("tasks")
        if isinstance(tasks, list):
            yield from _iter_steps(tasks)
