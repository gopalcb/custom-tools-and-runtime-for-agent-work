"""Compatibility facade for the refactored shared workflow runtime.

Workflow models, resolution functions, and the runner now live in the adjacent
``workflows`` package. Existing callers can continue importing this module.
"""

from .workflows.model import (
    StepHandler,
    WorkflowCancelled,
    WorkflowConfigurationError,
    WorkflowContext,
    WorkflowResult,
    WorkflowSelection,
)
from .workflows.workflow_runner import WorkflowEngine

__all__ = [
    "StepHandler",
    "WorkflowCancelled",
    "WorkflowConfigurationError",
    "WorkflowContext",
    "WorkflowEngine",
    "WorkflowResult",
    "WorkflowSelection",
]
