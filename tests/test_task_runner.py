from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import yaml

from agents_internal_messaging import AgentMessage, MessageBus
from agent_monorepo.events import RuntimeEvent
from agent_monorepo.planned_tasks import persist_planned_tasks
from agent_monorepo.task_runner import run_task_message


def sample_plan() -> dict:
    return {
        "workflow_id": "default",
        "title": "Runner Linked Plan",
        "summary": "Track task runner status.",
        "tasks": [
            {
                "name": "runner-task",
                "title": "Runner task",
                "description": "Execute a planned task.",
                "files": ["agent-runtime/agent-monorepo/task_runner.py"],
                "depends_on": [],
                "acceptance_criteria": [],
            }
        ],
    }


class FakeGateway:
    def __init__(self, events: list[RuntimeEvent]) -> None:
        self.events = events
        self.closed = False

    async def run(self, _prompt: str, run_id: str, session_id: str, agent_id: str):
        for event in self.events:
            yield event

    async def close(self) -> None:
        self.closed = True


def runtime_event(event_type: str, message: str | None = None) -> RuntimeEvent:
    return RuntimeEvent(
        seq=1,
        type=event_type,
        ts="2026-01-01T00:00:00Z",
        run_id="run-task-1",
        session_id="session-task-1",
        agent_id="agent-monorepo",
        message=message,
    )


class TaskRunnerPlannedTaskTests(unittest.TestCase):
    def test_successful_runner_updates_linked_planned_task_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = persist_planned_tasks(root, sample_plan())
            bus = MessageBus(root / ".agent-state" / "agents-messaging")
            message_path = bus.send(
                AgentMessage(
                    sender="monorepo-controller",
                    recipient="agent-monorepo",
                    type="task_request",
                    payload={
                        "task_id": "task-1",
                        "title": "Runner task",
                        "prompt": "Execute runner task.",
                        "plan_id": "runner-linked-plan",
                        "planned_task_id": "runner-task",
                    },
                )
            )
            gateway = FakeGateway([runtime_event("run.started"), runtime_event("run.completed", "Done.")])

            with patch("agent_monorepo.task_runner.initialize_project", return_value=SimpleNamespace(gateway=gateway)):
                result = asyncio.run(
                    run_task_message(
                        SimpleNamespace(
                            project_root=str(root),
                            message_path=str(message_path),
                            task_id="task-1",
                            agent_id="agent-monorepo",
                            run_id="run-task-1",
                            session_id="session-task-1",
                        )
                    )
                )
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        self.assertTrue(gateway.closed)
        self.assertEqual("complete", manifest["tasks"][0]["status"])
        self.assertEqual("run-task-1", manifest["tasks"][0]["run_id"])

    def test_failed_runner_updates_linked_planned_task_need_rework(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = persist_planned_tasks(root, sample_plan())
            bus = MessageBus(root / ".agent-state" / "agents-messaging")
            message_path = bus.send(
                AgentMessage(
                    sender="monorepo-controller",
                    recipient="agent-monorepo",
                    type="task_request",
                    payload={
                        "task_id": "task-1",
                        "title": "Runner task",
                        "prompt": "Execute runner task.",
                        "plan_id": "runner-linked-plan",
                        "planned_task_id": "runner-task",
                    },
                )
            )
            gateway = FakeGateway([runtime_event("run.started"), runtime_event("run.failed", "Needs work.")])

            with patch("agent_monorepo.task_runner.initialize_project", return_value=SimpleNamespace(gateway=gateway)):
                result = asyncio.run(
                    run_task_message(
                        SimpleNamespace(
                            project_root=str(root),
                            message_path=str(message_path),
                            task_id="task-1",
                            agent_id="agent-monorepo",
                            run_id="run-task-1",
                            session_id="session-task-1",
                        )
                    )
                )
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(1, result)
        self.assertEqual("need rework", manifest["tasks"][0]["status"])


if __name__ == "__main__":
    unittest.main()
