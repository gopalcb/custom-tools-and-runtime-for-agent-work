"""
Compact workflow resolver and async executor for custom agent runtimes.

YAML definitions live in `yamls/`; this module expands step references,
validates ordering and dependencies, and executes steps through caller-provided
handlers without depending on the full monorepo gateway.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


YAML_ROOT = Path(__file__).resolve().parent / "yamls"
SUPPORTED_USES = frozenset({"agent", "tool", "shell", "hook", "parallel", "conditional-parallel", "message", "workflow", "controller"})
WORKFLOW_DIRECTIVE = re.compile(r'(?:"workflow_id"|workflow_id)\s*[:=]\s*["`]?([a-z0-9]+(?:-[a-z0-9]+)*)', re.IGNORECASE)
StepHandler = Callable[[dict[str, Any], "WorkflowContext"], Awaitable[Any]]


class WorkflowConfigurationError(ValueError):
    """Raised when a workflow cannot be resolved or executed."""


class WorkflowCancelled(RuntimeError):
    """Raised when a workflow cancellation signal is set."""


@dataclass
class WorkflowContext:
    """Runtime state required by compact workflow steps."""

    run_id: str
    session_id: str
    agent_id: str
    conditions: dict[str, bool] = field(default_factory=dict)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    background_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowResult:
    """Terminal status and outputs for one workflow run."""

    status: str
    steps: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class WorkflowSelection:
    """Execution workflow chosen during planning."""

    workflow_id: str
    source: str


def load_yaml(path: str | Path) -> dict:
    """Load a YAML mapping from disk."""
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise WorkflowConfigurationError(f"YAML root must be a mapping: {path}")
    return payload


def load_catalogs(yaml_root: str | Path = YAML_ROOT) -> tuple[dict, dict]:
    """Load workflow and step catalogs from the YAML directory."""
    root = Path(yaml_root)
    workflow_doc = load_yaml(root / "workflow-orchestrator.yaml")
    step_doc = load_yaml(root / "workflow-steps.yaml")
    workflows = workflow_doc.get("workflows") if isinstance(workflow_doc.get("workflows"), dict) else {}
    steps = step_doc.get("steps") if isinstance(step_doc.get("steps"), dict) else {}
    if not workflows:
        raise WorkflowConfigurationError("workflow-orchestrator.yaml contains no workflows")
    return workflows, steps


def normalize_workflow_id(value: Any) -> str:
    """Normalize workflow IDs and `*-wf` aliases."""
    workflow_id = str(value or "analysis").strip()
    if workflow_id.endswith("-wf"):
        workflow_id = workflow_id[:-3]
    if not workflow_id:
        raise WorkflowConfigurationError("workflow is required")
    return workflow_id


def resolve_step_references(steps: list[Any], catalog: Mapping[str, Any]) -> list[dict]:
    """Expand catalog refs into independent workflow step mappings."""
    resolved = []
    for raw_step in steps:
        if not isinstance(raw_step, dict):
            raise WorkflowConfigurationError("Each workflow step must be a mapping")
        reference = raw_step.get("ref")
        if reference is None:
            resolved.append(dict(raw_step))
            continue
        if set(raw_step) != {"ref"} or not isinstance(reference, str) or not reference:
            raise WorkflowConfigurationError("A workflow step reference must contain only a non-empty ref")
        template = catalog.get(reference)
        if not isinstance(template, dict):
            raise WorkflowConfigurationError(f"Unknown workflow step reference: {reference!r}")
        resolved.append(dict(template))
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
            raise WorkflowConfigurationError(f"Step '{step_id}' depends on later or unknown steps: {', '.join(unknown)}")
        known.add(step_id)


def resolve_workflow(workflow_id: str, yaml_root: str | Path = YAML_ROOT) -> dict:
    """Resolve a workflow definition with expanded step refs."""
    workflows, step_catalog = load_catalogs(yaml_root)
    normalized = normalize_workflow_id(workflow_id)
    workflow = workflows.get(normalized)
    if not isinstance(workflow, dict):
        known = ", ".join(sorted(workflows))
        raise WorkflowConfigurationError(f"Unsupported workflow: {normalized}. Known workflows: {known}")
    resolved = dict(workflow)
    resolved["id"] = normalized
    resolved["steps"] = resolve_step_references(list(workflow.get("steps", [])), step_catalog)
    validate_steps(resolved["steps"])
    return resolved


def resolve_workflow_request(project_root: str | Path, payload: dict) -> dict:
    """Resolve a workflow message to stable workflow and step records."""
    workflow_id = normalize_workflow_id(payload.get("workflow") or payload.get("workflow_id"))
    yaml_root = Path(payload.get("yaml_root") or Path(__file__).resolve().parent / "yamls")
    workflow = resolve_workflow(workflow_id, yaml_root)
    return {
        "workflow": workflow["id"],
        "status": "resolved",
        "phase": workflow.get("phase"),
        "agent": payload.get("agent"),
        "steps": [
            {
                "id": step.get("id"),
                "name": step.get("name", step.get("id")),
                "uses": step.get("uses"),
                "status": step.get("status", "pending"),
                "inputs": step.get("inputs", {}),
                "outputs": step.get("outputs", {}),
            }
            for step in workflow["steps"]
        ],
        "execution_owner": "my-system-libs/workflow/engine.py",
        "project_root": str(Path(project_root).resolve()),
    }


def condition_met(condition: Any, context: WorkflowContext) -> bool:
    """Return whether a named runtime condition permits a step."""
    if condition is None:
        return True
    if not isinstance(condition, str) or not condition:
        raise WorkflowConfigurationError("Step condition must be a named flag")
    return bool(context.conditions.get(condition, False))


def max_attempts(step: Mapping[str, Any]) -> int:
    """Read and validate a step retry count."""
    retry = step.get("retry") or {}
    if not isinstance(retry, dict):
        raise WorkflowConfigurationError("retry must be a mapping")
    attempts = retry.get("max_attempts", 1)
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise WorkflowConfigurationError("retry.max_attempts must be a positive integer")
    return attempts


def timeout_seconds(step: Mapping[str, Any]) -> float | None:
    """Read and validate an optional positive timeout."""
    value = step.get("timeout")
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise WorkflowConfigurationError("timeout must be a positive number")
    return float(value)


def retryable(error: Exception) -> bool:
    """Return whether a failed step can be retried safely."""
    return not isinstance(error, (WorkflowConfigurationError, WorkflowCancelled, PermissionError, ValueError))


def check_cancelled(context: WorkflowContext) -> None:
    """Raise when the shared cancellation event is set."""
    if context.cancel_event.is_set():
        raise WorkflowCancelled("Run cancelled")


def resolve_planned_workflow(planner_response: str, available_workflows: set[str], fallback_workflow: str) -> WorkflowSelection:
    """Choose a valid planner workflow directive or retain fallback."""
    if fallback_workflow not in available_workflows:
        raise WorkflowConfigurationError(f"Fallback workflow is not available: {fallback_workflow}")
    match = WORKFLOW_DIRECTIVE.search(planner_response)
    if match and match.group(1) in available_workflows:
        return WorkflowSelection(match.group(1), "planner")
    return WorkflowSelection(fallback_workflow, "resolver-fallback")


class WorkflowEngine:
    """Execute ordered workflow steps with bounded parallel groups."""

    def __init__(self, max_parallel_tasks: int = 3) -> None:
        """Create a compact workflow engine."""
        if max_parallel_tasks < 1:
            raise ValueError("max_parallel_tasks must be positive")
        self.max_parallel_tasks = max_parallel_tasks

    async def execute(self, definition: Mapping[str, Any], context: WorkflowContext, handlers: Mapping[str, StepHandler]) -> WorkflowResult:
        """Execute a validated workflow definition."""
        steps = definition.get("steps")
        if not isinstance(steps, list):
            raise WorkflowConfigurationError("workflow.steps must be a list")
        validate_steps(steps)
        result = WorkflowResult(status="running")
        await self.emit("workflow.started", context, status="running")
        try:
            for step in steps:
                check_cancelled(context)
                step_id = step["id"]
                unmet = [dependency for dependency in step.get("depends_on", []) if result.steps.get(dependency) not in {"completed", "skipped"}]
                if unmet:
                    raise WorkflowConfigurationError(f"Step '{step_id}' has unmet dependencies: {', '.join(unmet)}")
                if not condition_met(step.get("when"), context):
                    result.steps[step_id] = "skipped"
                    await self.emit("workflow.step.completed", context, step_id=step_id, status="skipped", message=f"Skipped {step.get('name', step_id)}")
                    continue
                result.outputs[step_id] = await self.run_step(step, context, handlers)
                result.steps[step_id] = "completed"
            result.status = "completed"
            await self.emit("workflow.completed", context, status="completed")
        except (asyncio.CancelledError, WorkflowCancelled):
            result.status = "cancelled"
            raise
        except Exception:
            result.status = "failed"
            raise
        finally:
            result.events = list(context.events)
        return result

    async def run_step(self, step: dict[str, Any], context: WorkflowContext, handlers: Mapping[str, StepHandler]) -> Any:
        """Run one step with retry and timeout policy."""
        attempts = max_attempts(step)
        step_timeout = timeout_seconds(step)
        for attempt in range(1, attempts + 1):
            check_cancelled(context)
            await self.emit("workflow.step.started", context, step_id=step["id"], status="running", message=step.get("name"), payload={"attempt": attempt})
            try:
                output = await self.await_operation(self.dispatch(step, context, handlers), context, step_timeout)
                await self.emit("workflow.step.completed", context, step_id=step["id"], status="completed", message=step.get("name"), payload={"attempt": attempt})
                return output
            except Exception as error:
                will_retry = attempt < attempts and retryable(error)
                await self.emit("workflow.step.failed", context, step_id=step["id"], status="failed", message=str(error), payload={"attempt": attempt, "will_retry": will_retry})
                if not will_retry:
                    raise
        raise AssertionError("retry loop exited unexpectedly")

    async def await_operation(self, operation: Awaitable[Any], context: WorkflowContext, step_timeout: float | None) -> Any:
        """Await a step while honoring cancellation and timeout."""
        operation_task = asyncio.create_task(operation)
        cancellation_task = asyncio.create_task(context.cancel_event.wait())
        try:
            done, pending = await asyncio.wait({operation_task, cancellation_task}, timeout=step_timeout, return_when=asyncio.FIRST_COMPLETED)
            if cancellation_task in done and cancellation_task.result():
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
                raise WorkflowCancelled("Run cancelled")
            if operation_task not in done:
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
                raise asyncio.TimeoutError(f"Step timed out after {step_timeout} seconds")
            return await operation_task
        finally:
            for task in (operation_task, cancellation_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation_task, cancellation_task, return_exceptions=True)

    async def dispatch(self, step: dict[str, Any], context: WorkflowContext, handlers: Mapping[str, StepHandler]) -> Any:
        """Dispatch a normal step or bounded parallel group."""
        if step["uses"] not in {"parallel", "conditional-parallel"}:
            handler = handlers.get(step["uses"])
            if handler is None:
                return {"ok": True, "dry_run": True, "step": step}
            return await handler(step, context)
        tasks = step.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise WorkflowConfigurationError(f"{step['uses']} step '{step['id']}' requires non-empty tasks")
        if step["uses"] == "conditional-parallel":
            tasks = [task for task in tasks if condition_met(task.get("when"), context)]
            if not tasks:
                return {}
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)

        async def run_child(child: dict[str, Any]) -> tuple[str, Any]:
            """Run one child task in a parallel group."""
            child = dict(child)
            child["id"] = f"{step['id']}.{child['id']}"
            async with semaphore:
                return child["id"], await self.run_step(child, context, handlers)

        return dict(await asyncio.gather(*(run_child(child) for child in tasks)))

    async def emit(self, event_type: str, context: WorkflowContext, step_id: str | None = None, status: str | None = None, message: str | None = None, payload: Mapping[str, Any] | None = None) -> None:
        """Append one compact workflow event to the context."""
        context.events.append(
            {
                "type": event_type,
                "run_id": context.run_id,
                "session_id": context.session_id,
                "agent_id": context.agent_id,
                "step_id": step_id,
                "status": status,
                "message": message,
                "payload": dict(payload or {}),
            }
        )


async def run_workflow(workflow_id: str, prompt: str = "", agent_id: str = "compact-agent", conditions: dict[str, bool] | None = None, yaml_root: str | Path = YAML_ROOT) -> dict:
    """Resolve and dry-run a workflow with compact default handlers."""
    definition = resolve_workflow(workflow_id, yaml_root)
    context = WorkflowContext(
        run_id=f"run-{definition['id']}",
        session_id=f"session-{definition['id']}",
        agent_id=agent_id,
        conditions=dict(conditions or {}),
    )
    result = await WorkflowEngine().execute(definition, context, {})
    return {"prompt": prompt, "status": result.status, "steps": result.steps, "outputs": result.outputs, "events": result.events}


def main(argv: list[str] | None = None) -> int:
    """Run workflow resolution or dry execution from the command line."""
    parser = argparse.ArgumentParser(description="Compact workflow resolver/runner")
    parser.add_argument("--yaml-root", default=str(YAML_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--workflow", default="analysis")
    execute = sub.add_parser("run")
    execute.add_argument("--workflow", default="analysis")
    execute.add_argument("--prompt", default="")
    args = parser.parse_args(argv)
    if args.command == "resolve":
        result = resolve_workflow_request(".", {"workflow": args.workflow, "yaml_root": args.yaml_root})
    else:
        result = asyncio.run(run_workflow(args.workflow, args.prompt, yaml_root=args.yaml_root))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
