"""Resolve declarative workflow references and planning workflow choices.

The registry expands references from the adjacent ``workflow-steps.yaml``
catalog before execution. After planning, this module accepts an explicit
planner workflow directive only when it names an available execution workflow.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .model import (
    WorkflowCancelled,
    WorkflowConfigurationError,
    WorkflowContext,
    WorkflowSelection,
)


SUPPORTED_USES = frozenset({"agent", "tool", "shell", "hook", "parallel"})
WORKFLOW_DIRECTIVE = re.compile(
    r'(?:"workflow_id"|workflow_id)\s*[:=]\s*["`]?([a-z0-9]+(?:-[a-z0-9]+)*)',
    re.IGNORECASE,
)


def resolve_step_references(steps: list[Any], catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand catalog step references into independent workflow step mappings."""
    resolved: list[dict[str, Any]] = []
    for raw_step in steps:
        if not isinstance(raw_step, dict):
            raise WorkflowConfigurationError("Each workflow step must be a mapping")
        reference = raw_step.get("ref")
        if reference is None:
            resolved.append(deepcopy(raw_step))
            continue
        if set(raw_step) != {"ref"} or not isinstance(reference, str) or not reference:
            raise WorkflowConfigurationError("A workflow step reference must contain only a non-empty ref")
        template = catalog.get(reference)
        if not isinstance(template, dict):
            raise WorkflowConfigurationError(f"Unknown workflow step reference: {reference!r}")
        resolved.append(deepcopy(template))
    return resolved


def validate_steps(steps: list[Any]) -> None:
    """Validate ordered step ids, supported uses, and backward dependencies."""
    known: set[str] = set()
    for raw in steps:
        if not isinstance(raw, dict):
            raise WorkflowConfigurationError("Each workflow step must be a mapping")
        step_id = raw.get("id")
        uses = raw.get("uses")
        if not isinstance(step_id, str) or not step_id:
            raise WorkflowConfigurationError("Each workflow step needs a non-empty id")
        if step_id in known:
            raise WorkflowConfigurationError(f"Duplicate workflow step id: {step_id}")
        if uses not in SUPPORTED_USES:
            raise WorkflowConfigurationError(f"Step '{step_id}' uses unsupported type: {uses!r}")
        dependencies = raw.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise WorkflowConfigurationError(f"Step '{step_id}'.depends_on must be a list of step ids")
        unknown = [item for item in dependencies if item not in known]
        if unknown:
            raise WorkflowConfigurationError(
                f"Step '{step_id}' depends on later or unknown steps: {', '.join(unknown)}"
            )
        known.add(step_id)


def condition_met(condition: Any, context: WorkflowContext) -> bool:
    """Return whether a named runtime condition permits a step to run."""
    if condition is None:
        return True
    if not isinstance(condition, str) or not condition:
        raise WorkflowConfigurationError("Step condition must be a named flag")
    return bool(context.conditions.get(condition, False))


def max_attempts(step: Mapping[str, Any]) -> int:
    """Read and validate the retry count for one step."""
    retry = step.get("retry") or {}
    if not isinstance(retry, dict):
        raise WorkflowConfigurationError("retry must be a mapping")
    attempts = retry.get("max_attempts", 1)
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise WorkflowConfigurationError("retry.max_attempts must be a positive integer")
    return attempts


def timeout(step: Mapping[str, Any]) -> float | None:
    """Read and validate an optional positive step timeout."""
    value = step.get("timeout")
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise WorkflowConfigurationError("timeout must be a positive number")
    return float(value)


def retryable(error: Exception) -> bool:
    """Return whether a failure may be retried safely."""
    return not isinstance(error, (WorkflowConfigurationError, WorkflowCancelled, PermissionError, ValueError))


def check_cancelled(context: WorkflowContext) -> None:
    """Raise the shared cancellation exception when a run was cancelled."""
    if context.cancel_event.is_set():
        raise WorkflowCancelled("Run cancelled")


def resolve_planned_workflow(
    planner_response: str, available_workflows: set[str], fallback_workflow: str
) -> WorkflowSelection:
    """Choose the planner directive when valid, otherwise retain the fallback."""
    if fallback_workflow not in available_workflows:
        raise WorkflowConfigurationError(
            f"Fallback workflow is not an available execution workflow: {fallback_workflow}"
        )
    match = WORKFLOW_DIRECTIVE.search(planner_response)
    if match is not None and match.group(1) in available_workflows:
        return WorkflowSelection(workflow_id=match.group(1), source="planner")
    return WorkflowSelection(workflow_id=fallback_workflow, source="resolver-fallback")
