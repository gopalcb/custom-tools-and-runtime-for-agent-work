"""Construct the local agent application object graph and project context."""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway import AgentGateway

from .events import EventHub
from .logging_config import configure_runtime_logging
from .memory.service import MemoryPolicy, MemoryService
from .registry import Registry
from .resolver import Resolver
from .runtime import AgentRuntime, CodexAppServerClient
from .workflow import WorkflowEngine


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """Project startup details needed by runtime callers."""

    root: Path
    native_codex_bin: Path
    registry: Registry
    gateway: AgentGateway


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the nearest directory containing the project registry."""
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "project-registry.yaml").is_file()
            and (candidate / "agent-config" / "agents").is_dir()
        ):
            return candidate
    raise FileNotFoundError("Could not locate project-registry.yaml and agent-config/agents/.")


def initialize_project(project_root: str | Path | None = None) -> ProjectContext:
    """Build the runtime gateway and return project startup context."""
    root = find_project_root(project_root)
    native_codex_bin = resolve_native_codex(root)
    gateway = bootstrap(root, native_codex_bin=native_codex_bin)
    registry = gateway.runtime.registry
    return ProjectContext(root=root, native_codex_bin=native_codex_bin, registry=registry, gateway=gateway)


def resolve_native_codex(
    project_root: str | Path | None = None,
    configured: str | Path | None = None,
) -> Path:
    """Resolve the real Codex executable while excluding this repository wrapper."""
    root = find_project_root(project_root)
    wrapper = (root / "bin" / "codex").resolve()
    configured_value = configured or os.environ.get("CODEX_NATIVE_BIN")
    if configured_value:
        candidate = Path(configured_value).expanduser().resolve()
        if candidate == wrapper:
            raise RuntimeError("CODEX_NATIVE_BIN points at the monorepo wrapper, not native Codex.")
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise RuntimeError(f"Configured native Codex executable is not runnable: {candidate}")

    candidates: list[Path] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = (Path(directory).expanduser() / "codex").resolve()
        if candidate in candidates or candidate == wrapper:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            candidates.append(candidate)
    if candidates:
        return candidates[0]

    fallback = shutil.which("codex")
    if fallback:
        candidate = Path(fallback).resolve()
        if candidate != wrapper:
            return candidate
    raise RuntimeError(
        "Codex native executable could not be resolved. Configure CODEX_NATIVE_BIN "
        "or make sure native codex appears on PATH before monorepo/bin."
    )


def bootstrap(
    project_root: str | Path | None = None,
    native_codex_bin: str | Path | None = None,
) -> AgentGateway:
    """Build and return the thin gateway over the shared runtime."""
    root = find_project_root(project_root)
    log_path = configure_runtime_logging()
    logger.info("Bootstrapping agent runtime", extra={"project_root": str(root), "log_path": str(log_path)})
    registry = Registry(root)
    config = registry.project_config
    runtime_config = _mapping(config.get("runtime"), "runtime")
    codex_config = _mapping(config.get("codex"), "codex")
    memory_config = _mapping(config.get("memory"), "memory")

    events = EventHub(registry.state_root)
    start_log_analyzer_if_available(registry.agents_root, root, registry.state_root)
    memory = MemoryService(
        registry.state_root / "cache" / "memory",
        MemoryPolicy(
            retrieval_enabled=bool(
                memory_config.get("enabled", False)
                and memory_config.get(
                    "retrieval",
                    memory_config.get("semantic_retrieval", False),
                )
            ),
            extraction_enabled=bool(
                memory_config.get("enabled", False) and memory_config.get("extraction", False)
            ),
        ),
    )
    resolver = Resolver(registry)
    workflow = WorkflowEngine(
        events,
        max_parallel_tasks=int(runtime_config.get("max_parallel_tasks", 3)),
    )
    working_directory = _safe_configured_path(
        root, codex_config.get("working_directory", "."), "codex.working_directory"
    )
    writable_roots = tuple(
        _safe_configured_path(root, value, "codex.writable_roots")
        for value in codex_config.get("writable_roots", ["."])
    )
    minimum, maximum = _parse_supported_range(
        str(codex_config.get("supported_cli", ">=0.153.4,<0.155.0"))
    )
    native_codex = resolve_native_codex(root, native_codex_bin)
    command = shlex.split(str(codex_config.get("command", "codex app-server")))
    if command and command[0] == "codex":
        command = [str(native_codex), *command[1:]]
    codex = CodexAppServerClient(
        command or [str(native_codex), "app-server"],
        cwd=working_directory,
        approval_policy=str(codex_config.get("approval_policy", "never")),
        sandbox=str(codex_config.get("sandbox", "workspace-write")),
        writable_roots=writable_roots,
        network_access=bool(codex_config.get("network_access", True)),
        min_version=minimum,
        max_version=maximum,
    )
    runtime = AgentRuntime(root, registry, resolver, events, memory, workflow, codex)
    logger.info("Agent runtime bootstrap completed")
    return AgentGateway(runtime)


def start_log_analyzer_if_available(agents_root: Path, root: Path, state_root: Path) -> None:
    """Start the agent log analyzer thread when its program is present."""
    analyzer_path = agents_root / "agent-logs-analyzer" / "log_analyzer.py"
    if not analyzer_path.is_file():
        logger.info("Log analyzer program not found", extra={"path": str(analyzer_path)})
        return

    module_name = "agent_logs_analyzer_program"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, analyzer_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load log analyzer program: {analyzer_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    ensure_running = getattr(module, "ensure_log_analyzer_running", None)
    if not callable(ensure_running):
        raise RuntimeError(f"Log analyzer program has no ensure_log_analyzer_running: {analyzer_path}")
    started = bool(ensure_running(root, state_root))
    logger.info("Log analyzer startup checked", extra={"started": started})


def _safe_configured_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError(f"{label} must be a non-empty path")
    raw = Path(value)
    path = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"{label} escapes the project root: {value}")
    return path


def _parse_supported_range(value: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    match = re.fullmatch(
        r"\s*>=(\d+)\.(\d+)\.(\d+)\s*,\s*<(\d+)\.(\d+)\.(\d+)\s*",
        value,
    )
    if not match:
        raise ValueError("codex.supported_cli must use the form >=X.Y.Z,<A.B.C")
    values = tuple(int(part) for part in match.groups())
    minimum, maximum = values[:3], values[3:]
    if minimum >= maximum:
        raise ValueError("codex.supported_cli lower bound must precede its upper bound")
    return minimum, maximum


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} configuration must be a mapping")
    return value
