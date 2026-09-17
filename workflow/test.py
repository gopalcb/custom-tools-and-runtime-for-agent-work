"""
Smoke tests for compact workflow resolution and dry execution.
"""

from __future__ import annotations

import asyncio

from engine import WorkflowContext, WorkflowEngine, resolve_workflow, run_workflow


def test_resolve_and_dry_run() -> None:
    """Verify YAML expansion and default dry-run execution."""
    resolved = resolve_workflow("analysis")
    assert resolved["id"] == "analysis"
    assert [step["id"] for step in resolved["steps"]] == ["pre-work-health", "analyze"]
    result = asyncio.run(run_workflow("analysis", "Prompt"))
    assert result["status"] == "completed"


def test_custom_handler_execution() -> None:
    """Verify callers can provide handlers for real step execution."""
    async def handle_agent(step: dict, context: WorkflowContext) -> dict:
        return {"agent": step.get("agent"), "run_id": context.run_id}

    async def handle_controller(step: dict, context: WorkflowContext) -> dict:
        return {"action": step.get("action"), "run_id": context.run_id}

    resolved = resolve_workflow("analysis")
    context = WorkflowContext("run-test", "session-test", "agent-test")
    result = asyncio.run(WorkflowEngine().execute(resolved, context, {"agent": handle_agent, "controller": handle_controller}))
    assert result.status == "completed"
    assert result.outputs["analyze"]["agent"] == "analysis-agent"


def main() -> int:
    """Run workflow smoke tests."""
    test_resolve_and_dry_run()
    test_custom_handler_execution()
    print("workflow tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
