"""Construct the local agent application object graph once."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gateway import AgentGateway

from .events import EventHub
from .memory.service import MemoryPolicy, MemoryService
from .registry import Registry
from .resolver import Resolver
from .runtime import AgentRuntime, CodexAppServerClient
from .workflow import WorkflowEngine


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the nearest directory containing the project registry."""
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "project-registry.yaml").is_file() and (candidate / "agents").is_dir():
            return candidate
    raise FileNotFoundError("Could not locate project-registry.yaml and agents/.")


def bootstrap(project_root: str | Path | None = None) -> AgentGateway:
    """Build and return the thin gateway over the shared runtime."""
    root = find_project_root(project_root)
    registry = Registry(root)
    config = registry.project_config
    runtime_config = _mapping(config.get("runtime"), "runtime")
    codex_config = _mapping(config.get("codex"), "codex")
    memory_config = _mapping(config.get("memory"), "memory")

    events = EventHub(registry.state_root)
    memory = MemoryService(
        registry.state_root / "cache" / "memory",
        MemoryPolicy(
            retrieval_enabled=bool(
                memory_config.get("enabled", False)
                and memory_config.get("semantic_retrieval", False)
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
        str(codex_config.get("supported_cli", ">=0.153.4,<0.154.0"))
    )
    codex = CodexAppServerClient(
        codex_config.get("command", "codex app-server"),
        cwd=working_directory,
        approval_policy=str(codex_config.get("approval_policy", "never")),
        sandbox=str(codex_config.get("sandbox", "workspace-write")),
        writable_roots=writable_roots,
        network_access=bool(codex_config.get("network_access", True)),
        min_version=minimum,
        max_version=maximum,
    )
    runtime = AgentRuntime(root, registry, resolver, events, memory, workflow, codex)
    return AgentGateway(runtime)


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
