from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_source_package() -> None:
    if "agent_monorepo" in sys.modules:
        return
    package_dir = ROOT / "agent-runtime" / "agent-monorepo"
    spec = importlib.util.spec_from_file_location(
        "agent_monorepo",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


_load_source_package()

from agent_monorepo.events import EventHub
from agent_monorepo.workflow import (
    WorkflowCancelled,
    WorkflowConfigurationError,
    WorkflowEngine,
)
from agent_monorepo.workflows.workflow_resolver import resolve_planned_workflow


@dataclass
class Context:
    run_id: str = "run-1"
    session_id: str = "session-1"
    agent_id: str = "test-agent"
    conditions: dict[str, bool] = field(default_factory=dict)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    background_tasks: dict[str, asyncio.Task[object]] = field(default_factory=dict)


class WorkflowEngineBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.events = EventHub(self.temporary.name)
        self.engine = WorkflowEngine(self.events, max_parallel_tasks=2)
        self.context = Context()

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    async def test_order_conditions_dependencies_outputs_and_events(self) -> None:
        calls: list[str] = []

        async def handler(step, _context):
            calls.append(step["id"])
            return f"output:{step['id']}"

        definition = {
            "steps": [
                {"id": "first", "uses": "tool"},
                {"id": "optional", "uses": "agent", "when": "enabled", "depends_on": ["first"]},
                {"id": "last", "uses": "hook", "depends_on": ["optional"]},
            ]
        }
        result = await self.engine.execute(
            definition, self.context, {"tool": handler, "agent": handler, "hook": handler}
        )

        self.assertEqual(["first", "last"], calls)
        self.assertEqual("completed", result.status)
        self.assertEqual(
            {"first": "completed", "optional": "skipped", "last": "completed"},
            result.steps,
        )
        self.assertEqual({"first": "output:first", "last": "output:last"}, result.outputs)
        events = self.events.load_run(self.context.run_id, self.context.session_id)
        self.assertEqual("workflow.started", events[0].type)
        self.assertEqual(["first", "optional", "last"], [event.step_id for event in events[1:4]])
        skipped = next(event for event in events if event.step_id == "optional" and event.status == "skipped")
        self.assertEqual("workflow.step.completed", skipped.type)
        self.assertEqual("workflow.completed", events[-1].type)

    async def test_transient_failure_retries_but_policy_failures_do_not(self) -> None:
        attempts = 0

        async def transient(_step, _context):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporary")
            return "recovered"

        result = await self.engine.execute(
            {"steps": [{"id": "retry", "uses": "tool", "retry": {"max_attempts": 3}}]},
            self.context,
            {"tool": transient},
        )
        self.assertEqual("recovered", result.outputs["retry"])
        starts = [
            event for event in self.events.load_run("run-1", "session-1")
            if event.type == "workflow.step.started"
        ]
        self.assertEqual([1, 2, 3], [event.payload["attempt"] for event in starts])

        for exception in (PermissionError("denied"), ValueError("deterministic")):
            calls = 0

            async def permanent(_step, _context):
                nonlocal calls
                calls += 1
                raise exception

            context = Context(run_id=f"run-{type(exception).__name__}")
            with self.assertRaises(type(exception)):
                await self.engine.execute(
                    {"steps": [{"id": "no-retry", "uses": "tool", "retry": {"max_attempts": 4}}]},
                    context,
                    {"tool": permanent},
                )
            self.assertEqual(1, calls)

    async def test_timeout_is_emitted_and_may_be_retried(self) -> None:
        calls = 0

        async def slow(_step, _context):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)

        with self.assertRaises(asyncio.TimeoutError):
            await self.engine.execute(
                {
                    "steps": [
                        {"id": "slow", "uses": "tool", "timeout": 0.005, "retry": {"max_attempts": 2}}
                    ]
                },
                self.context,
                {"tool": slow},
            )
        self.assertEqual(2, calls)
        failures = [
            event for event in self.events.load_run("run-1", "session-1")
            if event.type == "workflow.step.failed"
        ]
        self.assertEqual(2, len(failures))
        self.assertTrue(all(event.payload["exception"] == "TimeoutError" for event in failures))

    async def test_parallel_group_is_bounded_and_returns_child_outputs(self) -> None:
        active = 0
        peak = 0
        registered_names: set[str] = set()

        async def handler(step, context):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            registered_names.update(task.get_name() for task in context.background_tasks.values())
            await asyncio.sleep(0.01)
            active -= 1
            return step["id"]

        tasks = [{"id": f"child-{number}", "uses": "tool"} for number in range(5)]
        result = await self.engine.execute(
            {"steps": [{"id": "group", "uses": "parallel", "tasks": tasks}]},
            self.context,
            {"tool": handler},
        )

        self.assertEqual(2, peak)
        self.assertEqual(
            {f"group.child-{number}": f"group.child-{number}" for number in range(5)},
            result.outputs["group"],
        )
        self.assertEqual({f"group.child-{number}" for number in range(5)}, registered_names)
        self.assertEqual({}, self.context.background_tasks)
        events = self.events.load_run(self.context.run_id, self.context.session_id)
        progress = [event for event in events if event.type == "background.progress"]
        self.assertEqual(10, len(progress))
        for task_id in {f"group.child-{number}" for number in range(5)}:
            self.assertEqual(
                [0.0, 1.0],
                [event.payload["progress"] for event in progress if event.step_id == task_id],
            )

    async def test_pre_cancelled_run_never_invokes_a_handler(self) -> None:
        called = False

        async def handler(_step, _context):
            nonlocal called
            called = True

        self.context.cancel_event.set()
        with self.assertRaisesRegex(WorkflowCancelled, "cancelled"):
            await self.engine.execute(
                {"steps": [{"id": "work", "uses": "tool"}]},
                self.context,
                {"tool": handler},
            )
        self.assertFalse(called)

    async def test_cancellation_between_steps_stops_remaining_work(self) -> None:
        calls: list[str] = []

        async def handler(step, context):
            calls.append(step["id"])
            context.cancel_event.set()

        with self.assertRaises(WorkflowCancelled):
            await self.engine.execute(
                {"steps": [{"id": "one", "uses": "tool"}, {"id": "two", "uses": "tool"}]},
                self.context,
                {"tool": handler},
            )
        self.assertEqual(["one"], calls)

    async def test_cancellation_signal_interrupts_active_parallel_children(self) -> None:
        all_started = asyncio.Event()
        all_stopped = asyncio.Event()
        started: list[str] = []
        stopped: list[str] = []

        async def handler(step, _context):
            started.append(step["id"])
            if len(started) == 2:
                all_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(step["id"])
                if len(stopped) == 2:
                    all_stopped.set()

        execution = asyncio.create_task(
            self.engine.execute(
                {
                    "steps": [
                        {
                            "id": "group",
                            "uses": "parallel",
                            "tasks": [
                                {"id": "one", "uses": "tool"},
                                {"id": "two", "uses": "tool"},
                            ],
                        }
                    ]
                },
                self.context,
                {"tool": handler},
            )
        )
        await asyncio.wait_for(all_started.wait(), timeout=0.2)
        self.context.cancel_event.set()

        with self.assertRaises(WorkflowCancelled):
            await asyncio.wait_for(execution, timeout=0.1)
        await asyncio.wait_for(all_stopped.wait(), timeout=0.1)
        self.assertCountEqual(["group.one", "group.two"], stopped)
        self.assertEqual({}, self.context.background_tasks)

    async def test_parallel_failure_cancels_siblings_and_cleans_registry(self) -> None:
        sibling_started = asyncio.Event()
        sibling_stopped = asyncio.Event()

        async def handler(step, _context):
            if step["id"] == "group.failure":
                await sibling_started.wait()
                raise RuntimeError("child failed")
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_stopped.set()

        with self.assertRaisesRegex(RuntimeError, "child failed"):
            await self.engine.execute(
                {
                    "steps": [
                        {
                            "id": "group",
                            "uses": "parallel",
                            "tasks": [
                                {"id": "failure", "uses": "tool"},
                                {"id": "sibling", "uses": "tool"},
                            ],
                        }
                    ]
                },
                self.context,
                {"tool": handler},
            )

        self.assertTrue(sibling_stopped.is_set())
        self.assertEqual({}, self.context.background_tasks)
        events = self.events.load_run(self.context.run_id, self.context.session_id)
        failures = [event for event in events if event.type == "background.failed"]
        self.assertEqual(["group.failure"], [event.step_id for event in failures])

    async def test_invalid_dependency_condition_and_step_configuration_fail(self) -> None:
        cases = (
            ({"steps": [{"id": "one", "uses": "tool", "depends_on": ["later"]}]}, "later or unknown"),
            ({"steps": [{"id": "one", "uses": "unknown"}]}, "unsupported"),
            ({"steps": [{"id": "one", "uses": "tool", "when": True}]}, "named flag"),
            ({"steps": [{"id": "one", "uses": "parallel", "tasks": []}]}, "non-empty tasks"),
        )

        async def handler(_step, _context):
            return None

        for index, (definition, message) in enumerate(cases):
            with self.subTest(definition=definition):
                context = Context(run_id=f"invalid-{index}")
                with self.assertRaisesRegex(WorkflowConfigurationError, message):
                    await self.engine.execute(definition, context, {"tool": handler})


class WorkflowPlanningResolutionTests(unittest.TestCase):
    def test_planner_can_select_only_available_execution_workflows(self) -> None:
        available = {"codex-smoke", "default"}

        selected = resolve_planned_workflow("workflow_id: default", available, "codex-smoke")
        invalid = resolve_planned_workflow("workflow_id: unknown", available, "codex-smoke")

        self.assertEqual(("default", "planner"), (selected.workflow_id, selected.source))
        self.assertEqual(("codex-smoke", "resolver-fallback"), (invalid.workflow_id, invalid.source))


if __name__ == "__main__":
    unittest.main()
