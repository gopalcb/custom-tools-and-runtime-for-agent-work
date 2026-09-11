from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_validation_module():
    spec = importlib.util.spec_from_file_location(
        "planner_validation",
        ROOT / "agent-config" / "agents" / "agent-implementation-planner" / "validation.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


from agent_monorepo.planned_tasks import (
    persist_planned_tasks,
    update_planned_task_status,
    update_planned_tasks_from_report,
)


validation = load_validation_module()


def sample_plan(tasks: list[dict] | None = None) -> dict:
    return {
        "workflow_id": "default",
        "title": "Controller Task Visibility",
        "summary": "Make implementation tasks visible in the controller.",
        "assumptions": [],
        "tasks": (
            [
                {
                    "name": "persist-tasks",
                    "title": "Persist planned tasks",
                    "description": "Write planned tasks to the controller data store.",
                    "files": ["agent-runtime/agent-monorepo/planned_tasks.py"],
                    "depends_on": [],
                    "acceptance_criteria": ["tasks.yaml exists"],
                }
            ]
            if tasks is None
            else tasks
        ),
        "architecture": {
            "overview": "Planner output becomes controller state.",
            "tree": "repo/",
            "components": [],
            "data_flow": [],
        },
        "implementation": {
            "phases": [
                {
                    "id": "phase-1",
                    "name": "Build",
                    "goal": "Add tracking",
                    "tasks": [
                        {
                            "id": "persist-tasks",
                            "description": "Write task files.",
                            "files": ["agent-runtime/agent-monorepo/planned_tasks.py"],
                            "depends_on": [],
                        }
                    ],
                }
            ],
            "execution_groups": [],
        },
        "testing": [],
        "risks": [],
        "done_criteria": [],
    }


class PlannedTaskValidationTests(unittest.TestCase):
    def test_validates_one_or_more_tracked_tasks(self) -> None:
        validation.validate_plan(sample_plan())
        validation.validate_plan(
            sample_plan(
                [
                    {
                        "name": "schema",
                        "title": "Schema",
                        "description": "Add schema fields.",
                        "files": ["plan.schema.json"],
                        "depends_on": [],
                        "acceptance_criteria": [],
                    },
                    {
                        "name": "controller",
                        "title": "Controller",
                        "description": "Show tasks.",
                        "files": ["monorepo-data.service.ts"],
                        "depends_on": ["schema"],
                        "acceptance_criteria": [],
                    },
                ]
            )
        )

    def test_rejects_invalid_task_breakdowns(self) -> None:
        cases = [
            ([], "at least one planned task"),
            ([{"name": "bad name", "title": "Bad", "description": "Bad", "files": ["x"], "depends_on": []}], "lowercase"),
            (
                [
                    {"name": "one", "title": "One", "description": "One", "files": ["x"], "depends_on": []},
                    {"name": "one", "title": "One again", "description": "One", "files": ["x"], "depends_on": []},
                ],
                "Duplicate",
            ),
            ([{"name": "one", "title": "One", "description": "One", "files": ["x"], "depends_on": ["missing"]}], "unknown"),
            ([{"name": "one", "title": "One", "description": "One", "files": ["x"], "depends_on": ["one"]}], "itself"),
        ]
        for tasks, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validation.validate_plan(sample_plan(tasks))


class PlannedTaskPersistenceTests(unittest.TestCase):
    def test_persists_manifest_markdown_and_preserves_status_on_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = persist_planned_tasks(root, sample_plan())
            self.assertEqual(
                root.resolve() / "agent-runtime" / "controller-data-store" / "planned-tasks" / "controller-task-visibility" / "tasks.yaml",
                manifest_path,
            )
            self.assertTrue((manifest_path.parent / "persist-tasks.md").is_file())

            updated = update_planned_task_status(
                root,
                "controller-task-visibility",
                "persist-tasks",
                "complete",
                "Finished.",
                "run-1",
                "session-1",
            )
            self.assertEqual(manifest_path, updated)
            persist_planned_tasks(root, sample_plan())
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            markdown = (manifest_path.parent / "persist-tasks.md").read_text(encoding="utf-8")

        self.assertEqual("complete", manifest["tasks"][0]["status"])
        self.assertEqual("planned-task", manifest["tasks"][0]["label"])
        self.assertEqual("run-1", manifest["tasks"][0]["run_id"])
        self.assertIn("Status: `complete`", markdown)

    def test_updates_only_the_linked_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = sample_plan(
                [
                    {"name": "first", "title": "First", "description": "First task.", "files": ["a"], "depends_on": [], "acceptance_criteria": []},
                    {"name": "second", "title": "Second", "description": "Second task.", "files": ["b"], "depends_on": ["first"], "acceptance_criteria": []},
                ]
            )
            manifest_path = persist_planned_tasks(root, plan)
            update_planned_task_status(root, "controller-task-visibility", "second", "need rework", "Failed.", "run-2", "session-2")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        statuses = {task["id"]: task["status"] for task in manifest["tasks"]}
        self.assertEqual({"first": "awaiting implementation", "second": "need rework"}, statuses)

    def test_updates_task_statuses_from_agent_report_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = sample_plan(
                [
                    {"name": "first", "title": "First", "description": "First task.", "files": ["a"], "depends_on": [], "acceptance_criteria": []},
                    {"name": "second", "title": "Second", "description": "Second task.", "files": ["b"], "depends_on": ["first"], "acceptance_criteria": []},
                ]
            )
            manifest_path = persist_planned_tasks(root, plan)
            count = update_planned_tasks_from_report(
                root,
                "controller-task-visibility",
                "planned-task first: complete\nplanned-task `second`: need rework",
                "run-report",
                "session-report",
            )
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        statuses = {task["id"]: task["status"] for task in manifest["tasks"]}
        self.assertEqual(2, count)
        self.assertEqual({"first": "complete", "second": "need rework"}, statuses)


if __name__ == "__main__":
    unittest.main()
