"""Execute validated declarative workflow steps and publish RuntimeEvents.

Definition validation and condition handling live in ``workflow_resolver``;
this module owns retries, cancellation, dispatch, parallel work, and events.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Mapping
from typing import Any

from ..events import EventHub
from .model import (
    StepHandler,
    WorkflowCancelled,
    WorkflowConfigurationError,
    WorkflowContext,
    WorkflowResult,
)
from .workflow_resolver import (
    SUPPORTED_USES,
    check_cancelled,
    condition_met,
    max_attempts,
    retryable,
    timeout,
    validate_steps,
)


logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Execute ordered workflow steps with small, bounded parallel groups."""

    SUPPORTED_USES = SUPPORTED_USES

    def __init__(self, events: EventHub, max_parallel_tasks: int = 3) -> None:
        """Store event publishing and the configured parallel-work limit."""
        if max_parallel_tasks < 1:
            raise ValueError("max_parallel_tasks must be positive")
        self.events = events
        self.max_parallel_tasks = max_parallel_tasks
        logger.info("WorkflowEngine initialized", extra={"max_parallel_tasks": max_parallel_tasks})

    async def execute(
        self,
        definition: Mapping[str, Any],
        context: WorkflowContext,
        handlers: Mapping[str, StepHandler],
    ) -> WorkflowResult:
        """Execute validated workflow steps and return their outputs."""
        steps = definition.get("steps")
        if not isinstance(steps, list):
            raise WorkflowConfigurationError("workflow.steps must be a list")
        validate_steps(steps)
        result = WorkflowResult(status="running")
        await self.emit("workflow.started", context, status="running")
        logger.info("Workflow execution started", extra={"run_id": context.run_id})
        for step in steps:
            await self.emit(
                "workflow.step.queued",
                context,
                step_id=step["id"],
                status="queued",
                message=step.get("name"),
            )
        try:
            for step in steps:
                check_cancelled(context)
                step_id = step["id"]
                unmet = [
                    dependency
                    for dependency in step.get("depends_on", [])
                    if result.steps.get(dependency) not in {"completed", "skipped"}
                ]
                if unmet:
                    raise WorkflowConfigurationError(
                        f"Step '{step_id}' has unmet dependencies: {', '.join(unmet)}"
                    )
                if not condition_met(step.get("when"), context):
                    result.steps[step_id] = "skipped"
                    await self.emit(
                        "workflow.step.completed",
                        context,
                        step_id=step_id,
                        status="skipped",
                        message=f"Skipped {step.get('name', step_id)}",
                    )
                    continue
                result.outputs[step_id] = await self.run_step(step, context, handlers)
                result.steps[step_id] = "completed"
            result.status = "completed"
            await self.emit("workflow.completed", context, status="completed")
            logger.info("Workflow execution completed", extra={"run_id": context.run_id})
            return result
        except (asyncio.CancelledError, WorkflowCancelled):
            result.status = "cancelled"
            logger.info("Workflow execution cancelled", extra={"run_id": context.run_id})
            raise
        except Exception as error:
            result.status = "failed"
            logger.warning(
                "Workflow execution failed",
                extra={"run_id": context.run_id, "exception": type(error).__name__},
            )
            raise

    async def run_step(
        self, step: dict[str, Any], context: WorkflowContext, handlers: Mapping[str, StepHandler]
    ) -> Any:
        """Run one step with its configured retry and timeout policy."""
        step_id = step["id"]
        attempts = max_attempts(step)
        step_timeout = timeout(step)
        for attempt in range(1, attempts + 1):
            check_cancelled(context)
            await self.emit(
                "workflow.step.started",
                context,
                step_id=step_id,
                status="running",
                message=step.get("name"),
                payload={"attempt": attempt, "max_attempts": attempts},
            )
            logger.info(
                "Workflow step started",
                extra={"run_id": context.run_id, "step_id": step_id, "attempt": attempt},
            )
            try:
                output = await self.await_operation(
                    self.dispatch(step, context, handlers), context, step_timeout
                )
                await self.emit(
                    "workflow.step.completed",
                    context,
                    step_id=step_id,
                    status="completed",
                    message=step.get("name"),
                    payload={"attempt": attempt},
                )
                logger.info(
                    "Workflow step completed",
                    extra={"run_id": context.run_id, "step_id": step_id, "attempt": attempt},
                )
                return output
            except asyncio.CancelledError:
                raise
            except Exception as error:
                will_retry = attempt < attempts and retryable(error)
                logger.log(
                    logging.INFO if will_retry else logging.WARNING,
                    "Workflow step failed",
                    extra={
                        "run_id": context.run_id,
                        "step_id": step_id,
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "exception": type(error).__name__,
                        "will_retry": will_retry,
                    },
                )
                await self.emit(
                    "workflow.step.failed",
                    context,
                    step_id=step_id,
                    status="failed",
                    message=str(error),
                    payload={
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "exception": type(error).__name__,
                    },
                )
                if not will_retry:
                    raise
        raise AssertionError("retry loop exited unexpectedly")

    async def await_operation(
        self, operation: Awaitable[Any], context: WorkflowContext, step_timeout: float | None
    ) -> Any:
        """Await work while enforcing cancellation and an optional timeout."""
        operation_task = asyncio.create_task(operation)
        cancellation_task = asyncio.create_task(context.cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {operation_task, cancellation_task},
                timeout=step_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
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
            if not operation_task.done():
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
            if not cancellation_task.done():
                cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)

    async def dispatch(
        self, step: dict[str, Any], context: WorkflowContext, handlers: Mapping[str, StepHandler]
    ) -> Any:
        """Dispatch a normal handler or one bounded parallel group."""
        if step["uses"] != "parallel":
            handler = handlers.get(step["uses"])
            if handler is None:
                raise WorkflowConfigurationError(
                    f"No handler registered for step type '{step['uses']}'"
                )
            return await handler(step, context)
        tasks = step.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise WorkflowConfigurationError(
                f"Parallel step '{step['id']}' requires non-empty tasks"
            )
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)

        async def run_child(child: dict[str, Any]) -> tuple[str, Any]:
            """Run, report, and unregister one child task."""
            child = dict(child)
            child["id"] = f"{step['id']}.{child['id']}"
            task_id = child["id"]
            try:
                async with semaphore:
                    message = child.get("name", task_id)
                    await self.emit(
                        "background.started",
                        context,
                        step_id=task_id,
                        status="running",
                        message=message,
                        payload={"task_id": task_id, "command": child.get("command")},
                    )
                    await self.emit(
                        "background.progress",
                        context,
                        step_id=task_id,
                        status="running",
                        message=message,
                        payload={"task_id": task_id, "progress": 0.0},
                    )
                    output = await self.run_step(child, context, handlers)
                    await self.emit(
                        "background.progress",
                        context,
                        step_id=task_id,
                        status="running",
                        message=message,
                        payload={"task_id": task_id, "progress": 1.0},
                    )
                    await self.emit(
                        "background.completed",
                        context,
                        step_id=task_id,
                        status="completed",
                        message=message,
                        payload={"task_id": task_id, "progress": 1.0},
                    )
                    return task_id, output
            except Exception as error:
                await self.emit(
                    "background.failed",
                    context,
                    step_id=task_id,
                    status="failed",
                    message=str(error),
                    payload={"task_id": task_id},
                )
                raise
            finally:
                registry = getattr(context, "background_tasks", None)
                current = asyncio.current_task()
                if isinstance(registry, dict) and registry.get(task_id) is current:
                    registry.pop(task_id, None)

        child_tasks: list[asyncio.Task[tuple[str, Any]]] = []
        registry = getattr(context, "background_tasks", None)
        for child in tasks:
            task_id = f"{step['id']}.{child['id']}"
            child_task = asyncio.create_task(run_child(child), name=task_id)
            child_tasks.append(child_task)
            if isinstance(registry, dict):
                registry[task_id] = child_task
        logger.info(
            "Parallel workflow group started",
            extra={"run_id": context.run_id, "step_id": step["id"], "task_count": len(child_tasks)},
        )
        try:
            return dict(await asyncio.gather(*child_tasks))
        finally:
            for child_task in child_tasks:
                if not child_task.done():
                    child_task.cancel()
            await asyncio.gather(*child_tasks, return_exceptions=True)
            logger.info(
                "Parallel workflow group finalized",
                extra={"run_id": context.run_id, "step_id": step["id"]},
            )

    async def emit(
        self,
        event_type: str,
        context: WorkflowContext,
        step_id: str | None = None,
        status: str | None = None,
        message: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """Publish one workflow event through the shared RuntimeEvent hub."""
        await self.events.emit(
            self.events.new_event(
                event_type,
                run_id=context.run_id,
                session_id=context.session_id,
                agent_id=context.agent_id,
                step_id=step_id,
                status=status,
                message=message,
                payload=dict(payload or {}),
            )
        )
