from __future__ import annotations

import unittest
from pathlib import Path

from agent_monorepo.registry import Registry
from agent_monorepo.resolver import Resolver


ROOT = Path(__file__).resolve().parents[1]


class DefaultConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Registry(ROOT)
        self.resolver = Resolver(self.registry)

    def test_unqualified_prompt_starts_planning_before_the_default_workflow(self) -> None:
        resolved = self.resolver.resolve("Check runtime")

        self.assertEqual("agent-monorepo", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)
        self.assertEqual("workflow-selection", resolved.planning_workflow_id)
        self.assertEqual(
            ["pre-work-health", "analyze", "resolve-context", "web-research", "plan"],
            [step["id"] for step in self.registry.get_workflow("workflow-selection")["steps"]],
        )

    def test_default_workflow_checks_health_and_collects_strategy_feedback_before_finalization(self) -> None:
        workflow = self.registry.get_workflow("default")

        self.assertEqual(
            ["pre-work-health", "execute", "validate", "store-strategy-memory", "finalize"],
            [step["id"] for step in workflow["steps"]],
        )
        health_step = workflow["steps"][0]
        self.assertEqual("hook", health_step["uses"])
        self.assertEqual("pre_work_health_check", health_step["hook"])
        feedback_step = workflow["steps"][3]
        self.assertEqual("hook", feedback_step["uses"])
        self.assertEqual("strategy_memory_feedback", feedback_step["hook"])

    def test_all_execution_workflows_check_health_and_collect_strategy_feedback_before_finalization(self) -> None:
        for workflow_id in sorted(self.registry.execution_workflow_ids()):
            workflow = self.registry.get_workflow(workflow_id)
            steps = [step["id"] for step in workflow["steps"]]

            self.assertEqual("pre-work-health", steps[0], workflow_id)
            self.assertIn("store-strategy-memory", steps, workflow_id)
            self.assertIn("finalize", steps, workflow_id)
            self.assertLess(
                steps.index("store-strategy-memory"),
                steps.index("finalize"),
                workflow_id,
            )

    def test_explicit_skip_planning_bypasses_planning_workflow_only(self) -> None:
        resolved = self.resolver.resolve("Skip planning and check runtime")

        self.assertEqual("agent-monorepo", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)
        self.assertIsNone(resolved.planning_workflow_id)
        self.assertTrue(resolved.conditions["skip_planning"])

    def test_codex_agent_prefix_activates_generic_codex_agent(self) -> None:
        resolved = self.resolver.resolve("/codex-agent check runtime")

        self.assertEqual("codex-agent", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)

    def test_diag_builder_prefix_activates_html_diagram_agent(self) -> None:
        resolved = self.resolver.resolve("/diag-builder show the runtime event pipeline")

        self.assertEqual("diagram-builder", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)
        self.assertIn("diagram-builder", resolved.skills)

    def test_diagram_request_routes_to_html_diagram_agent(self) -> None:
        resolved = self.resolver.resolve("Write an HTML blog page and build diagram for the runtime")

        self.assertEqual("diagram-builder", resolved.agent_id)

    def test_markdown_article_with_diagram_does_not_route_to_diagram_builder(self) -> None:
        resolved = self.resolver.resolve("Write an article.md about runtime and create diagram notes")

        self.assertEqual("agent-monorepo", resolved.agent_id)

    def test_explicit_specialized_agent_still_selects_its_own_workflow(self) -> None:
        resolved = self.resolver.resolve("Create an HTML preview")

        self.assertEqual("agent-ui-builder", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)


if __name__ == "__main__":
    unittest.main()
