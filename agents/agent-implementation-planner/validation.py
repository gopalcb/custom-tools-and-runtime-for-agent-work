"""Validate planner CLI inputs and structured plan output.

This module keeps input and output checks separate from Codex invocation and
Markdown rendering in ``planner.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


REQUIRED_PLAN_KEYS = {
    "workflow_id",
    "title",
    "summary",
    "assumptions",
    "architecture",
    "implementation",
    "testing",
    "risks",
    "done_criteria",
}


def validate_cli_inputs(
    repo: str,
    output_dir: str,
    codex_bin: str,
    schema_path: Path,
    dry_run: bool,
) -> tuple[Path, Path, str]:
    """Validate planner paths and resolve the Codex executable."""
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        raise ValueError(f"Repository does not exist: {repo_path}")

    schema = schema_path.expanduser().resolve()
    if not schema.is_file():
        raise ValueError(f"Planner schema does not exist: {schema}")

    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = repo_path / output_path
    output_path = output_path.resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if not output_path.is_dir():
        raise ValueError(f"Planner output path is not a directory: {output_path}")

    resolved_codex = shutil.which(codex_bin) if codex_bin.strip() else None
    if not dry_run and codex_bin.strip() and resolved_codex is None:
        raise ValueError(f"Codex executable not found: {codex_bin}")
    return repo_path, output_path, resolved_codex or codex_bin


def validate_plan(plan: dict[str, Any]) -> None:
    """Validate the required semantic shape of a generated plan."""
    if not isinstance(plan, dict):
        raise ValueError("Planner output must be a JSON object")
    missing = REQUIRED_PLAN_KEYS.difference(plan)
    if missing:
        raise ValueError(f"Missing required planner fields: {sorted(missing)}")
    if not isinstance(plan["workflow_id"], str) or not plan["workflow_id"].strip():
        raise ValueError("Planner output must include a workflow_id")

    architecture = plan["architecture"]
    if not isinstance(architecture, dict) or not str(architecture.get("tree", "")).strip():
        raise ValueError("Planner output must include an architecture tree")
    components = architecture.get("components")
    if not isinstance(components, list):
        raise ValueError("Planner architecture.components must be a list")

    implementation = plan["implementation"]
    if not isinstance(implementation, dict):
        raise ValueError("Planner implementation must be an object")
    phases = implementation.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("Planner output must include implementation phases")

    task_ids: set[str] = set()
    for phase in phases:
        if not isinstance(phase, dict) or not isinstance(phase.get("tasks"), list):
            raise ValueError("Every planner phase must contain a tasks list")
        for task in phase["tasks"]:
            if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]:
                raise ValueError("Every planner task must have an ID")
            task_id = task["id"]
            if task_id in task_ids:
                raise ValueError(f"Duplicate task ID: {task_id}")
            task_ids.add(task_id)
            files = task.get("files")
            if not isinstance(files, list) or not files or not all(isinstance(path, str) and path for path in files):
                raise ValueError(f"Planner task {task_id} must identify affected files")
            dependencies = task.get("depends_on", task.get("dependencies", []))
            if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
                raise ValueError(f"Planner task {task_id} has invalid dependencies")
    if not task_ids:
        raise ValueError("Planner output must include at least one implementation task")
