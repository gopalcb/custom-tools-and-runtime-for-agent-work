"""Shared contracts for declarative workflow resolution and execution.

The resolver validates workflow definitions and selects an execution workflow;
the runner executes the resulting steps and publishes runtime events.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


class WorkflowConfigurationError(ValueError):
    """Raised when a workflow cannot be executed deterministically."""


class WorkflowCancelled(RuntimeError):
    """Raised when the shared run cancellation signal is set."""


class WorkflowContext(Protocol):
    """Describe the runtime state required by workflow steps."""

    run_id: str
    session_id: str
    agent_id: str
    conditions: Mapping[str, bool]
    cancel_event: asyncio.Event
    background_tasks: dict[str, asyncio.Task[Any]]


StepHandler = Callable[[dict[str, Any], WorkflowContext], Awaitable[Any]]


@dataclass(slots=True)
class WorkflowResult:
    """Capture the terminal status and outputs of one workflow execution."""

    status: str
    steps: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowSelection:
    """Record the execution workflow chosen during the planning phase."""

    workflow_id: str
    source: str
